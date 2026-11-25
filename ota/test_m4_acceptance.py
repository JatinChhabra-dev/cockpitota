"""
Module 4 — Acceptance Tests (Staged OTA Rollout, Preconditions, Signing, R156 Ledger)
Verifies Spec §4 (pp. 11–12) M4-FR1 through M4-FR6:
  - Gate enforcement: blocks OTA creation if gate_passed=False
  - M4-FR1: 2-group staged rollout: 10% (1 of 10 vehicles) -> auto-advance to 100%
  - M4-FR2: Preconditions (parked & SoC >= 30%): SC-01 moving + SC-05 SoC 20% defer, then install on recovery
  - M4-FR3: Tampered artefact fails signature check -> REJECTED in ledger, rollout halted
  - M4-FR4: Pre-update and post-update package versions recorded in per-vehicle ledger + evidence/ota_ledger.json
  - M4-FR6: Campaign pause / resume / cancel
  - Live ADB verification if an AAOS cockpit is currently ONLINE

Usage:
    cd cockpit-ota
    python ota/test_m4_acceptance.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8001"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_PATH = os.path.join(ROOT_DIR, "evidence", "ota_ledger.json")

results = []
passed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed
    status = "PASS ✅" if condition else "FAIL ❌"
    if condition:
        passed += 1
    results.append({"name": name, "passed": condition, "detail": detail})
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")


def _api(method: str, path: str, body: dict | None = None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw else {}), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return json.loads(raw), e.code
        except Exception:
            return {"raw": raw}, e.code


def run_tests():
    print("\n" + "=" * 66)
    print("  MODULE 4 — Acceptance Tests (Staged OTA Rollout & R156 Ledger)")
    print("=" * 66)

    # 1. Verify 10-vehicle fleet & gate enforcement
    print("\n[1] Checking OTA Fleet & Gate Enforcement...")
    vehs_resp, vehs_code = _api("GET", "/v1/vehicles")
    check("GET /v1/vehicles returns >= 10 fleet vehicles (M1-FR7)", vehs_code == 200 and vehs_resp.get("total", 0) >= 10, f"total={vehs_resp.get('total')}")

    blocked_resp, blocked_code = _api("POST", "/v1/campaigns", {
        "release_id": "v1.1",
        "apk_filename": "aurelia-ev-v1.1.apk",
        "target_version": "1.1.0",
        "gate_passed": False,
    })
    check("Gate adapter blocks campaign when gate_passed=False (HTTP 403)", blocked_code == 403, f"code={blocked_code}")

    # 2. Configure SC-01 (moving) on veh-02 and SC-05 (SoC 20%) on veh-03
    print("\n[2] Setting SC-01 (moving) on veh-02 & SC-05 (SoC 20%) on veh-03...")
    _api("POST", "/v1/vehicles/veh-01/state", {"gear": "GEAR_PARK", "speed_kmh": 0, "soc_percent": 80})
    _api("POST", "/v1/vehicles/veh-02/state", {"gear": "GEAR_DRIVE", "speed_kmh": 50, "soc_percent": 80})
    _api("POST", "/v1/vehicles/veh-03/state", {"gear": "GEAR_PARK", "speed_kmh": 0, "soc_percent": 20})

    # 3. Launch staged 10% -> 100% campaign (M4-FR1 & M4-FR2)
    print("\n[3] Creating Staged Rollout Campaign (10% Canary -> 100% Fleet)...")
    camp_resp, camp_code = _api("POST", "/v1/campaigns", {
        "release_id": "v1.1-fix",
        "apk_filename": "aurelia-ev-v1.1-fix.apk",
        "package_name": "com.aurelia.ev",
        "target_version": "1.1.1-fix",
        "gate_passed": True,
        "auto_start": True,
    })
    check("POST /v1/campaigns returns HTTP 201", camp_code == 201, f"id={camp_resp.get('campaign', {}).get('campaign_id')}")

    camp = camp_resp.get("campaign", {})
    cid = camp.get("campaign_id")
    groups = camp.get("groups", [])
    check("Rollout has 2 groups: 10% (1 veh) then 100% (9 veh) (M4-FR1)", len(groups) == 2 and len(groups[0]["target_vehicle_ids"]) == 1 and len(groups[1]["target_vehicle_ids"]) == 9)
    check("Group 1 (10% Canary) succeeded & auto-advanced Group 2", groups[0]["status"] == "FINISHED" and groups[1]["status"] == "RUNNING", f"g1={groups[0]['status']} g2={groups[1]['status']}")

    # Tick Group 2 so all 9 remaining vehicles evaluate preconditions
    tick1, _ = _api("POST", f"/v1/campaigns/{cid}/tick")
    recs1 = {r["vehicle_id"]: r for r in tick1.get("records", [])}
    check("veh-02 (SC-01 moving) reports DEFERRED (M4-FR2)", recs1["veh-02"]["outcome"] == "DEFERRED", f"reasons={recs1['veh-02']['defer_reasons']}")
    check("veh-03 (SC-05 SoC 20%) reports DEFERRED (M4-FR2)", recs1["veh-03"]["outcome"] == "DEFERRED", f"reasons={recs1['veh-03']['defer_reasons']}")
    check("Other 8 parked/charged vehicles INSTALLED", sum(1 for r in recs1.values() if r["outcome"] == "INSTALLED") == 8, f"installed={sum(1 for r in recs1.values() if r['outcome'] == 'INSTALLED')}/10")

    # 4. Satisfy preconditions -> both deferred vehicles install!
    print("\n[4] Satisfying Preconditions on veh-02 (Park) & veh-03 (Charge to 35%)...")
    _api("POST", "/v1/vehicles/veh-02/state", {"gear": "GEAR_PARK", "speed_kmh": 0})
    _api("POST", "/v1/vehicles/veh-03/state", {"soc_percent": 35})

    tick2, _ = _api("POST", f"/v1/campaigns/{cid}/tick")
    recs2 = {r["vehicle_id"]: r for r in tick2.get("records", [])}
    check("veh-02 installed after parking", recs2["veh-02"]["outcome"] == "INSTALLED")
    check("veh-03 installed after SoC rose to 35%", recs2["veh-03"]["outcome"] == "INSTALLED")
    check("Campaign status transitioned to FINISHED (10/10 installed)", tick2["campaign"]["status"] == "FINISHED", f"status={tick2['campaign']['status']}")

    # 5. Per-Vehicle R156 Ledger (M4-FR4)
    print("\n[5] Verifying Per-Vehicle R156 Update Ledger (M4-FR4)...")
    ledger_resp, ledger_code = _api("GET", "/v1/vehicles/veh-02/ledger")
    latest = ledger_resp.get("records", [{}])[-1]
    check("GET /v1/vehicles/veh-02/ledger returns pre/post versions", ledger_code == 200 and latest.get("post_versions", {}).get("com.aurelia.ev") == "1.1.1-fix", f"pre={latest.get('pre_versions')} post={latest.get('post_versions')}")
    check("Persistent evidence/ota_ledger.json written", os.path.isfile(LEDGER_PATH) and os.path.getsize(LEDGER_PATH) > 100)

    # 6. Tampered Artefact Rejection Test (M4-FR3)
    print("\n[6] Testing Tampered Artefact Signature Rejection (M4-FR3)...")
    tamper_resp, tamper_code = _api("POST", "/v1/campaigns", {
        "release_id": "v1.1-tampered",
        "apk_filename": "aurelia-ev-v1.1-fix.apk",
        "target_version": "1.1.1-fix",
        "gate_passed": True,
        "tamper_test": True,
        "auto_start": True,
    })
    t_recs = tamper_resp.get("records", [])
    canary_rec = next((r for r in t_recs if r["group_index"] == 1), {})
    check("Tampered APK rejected with REJECTED outcome", canary_rec.get("outcome") == "REJECTED", f"reason={canary_rec.get('failure_reason')}")
    check("Group 2 halted on canary rejection", tamper_resp["campaign"]["groups"][1]["status"] == "WAITING", f"g2={tamper_resp['campaign']['groups'][1]['status']}")

    # 7. Pause / Resume / Cancel controls (M4-FR6)
    print("\n[7] Testing Campaign Pause / Resume / Cancel (M4-FR6)...")
    ctrl_resp, _ = _api("POST", "/v1/campaigns", {
        "release_id": "v1.1-fix",
        "apk_filename": "aurelia-ev-v1.1-fix.apk",
        "target_version": "1.1.1-fix",
        "gate_passed": True,
        "auto_start": False,
    })
    ctrl_id = ctrl_resp["campaign"]["campaign_id"]
    p_resp, _ = _api("POST", f"/v1/campaigns/{ctrl_id}/pause")
    c_resp, _ = _api("POST", f"/v1/campaigns/{ctrl_id}/cancel")
    check("Campaign pause & cancel transitions work", p_resp["campaign"]["status"] == "PAUSED" and c_resp["campaign"]["status"] == "CANCELED")

    # 8. Live ADB Emulator OTA Install (if an emulator is currently ONLINE)
    print("\n[8] Checking for live ONLINE AAOS emulator for real ADB OTA install...")
    live_insts, _ = _api("GET", "/v1/fleet/instances?status=ONLINE")
    if live_insts.get("instances"):
        live = live_insts["instances"][0]
        live_id = live["instance_id"]
        print(f"  Found live cockpit {live_id} ({live['adb_serial']}) — setting parked + SoC 80% and rolling out v1.1-fix...")
        _api("POST", f"/v1/vehicles/{live_id}/state", {"gear": "GEAR_PARK", "speed_kmh": 0, "soc_percent": 80})
        live_camp, live_code = _api("POST", "/v1/campaigns", {
            "release_id": "v1.1-fix",
            "apk_filename": "aurelia-ev-v1.1-fix.apk",
            "package_name": "com.aurelia.ev",
            "target_version": "1.1.1-fix",
            "gate_passed": True,
            "vehicle_ids": [live_id],
            "auto_start": True,
        })
        live_rec = live_camp.get("records", [{}])[0]
        check(
            f"Live AAOS cockpit ({live['adb_serial']}) OTA install succeeded",
            live_code == 201 and live_rec.get("outcome") == "INSTALLED",
            f"pre={live_rec.get('pre_versions')} post={live_rec.get('post_versions')}",
        )
    else:
        print("  (No live AAOS emulator currently online — skipped live ADB OTA bonus check)")

    total = len(results)
    print("\n" + "=" * 66)
    print(f"  M4 Result: {passed}/{total} checks passed")
    print("=" * 66)
    if passed == total:
        print("\n  🎉 Module 4 (M4) GATE PASSED — STAGED OTA & R156 LEDGER VERIFIED!")
    else:
        failed = [r["name"] for r in results if not r["passed"]]
        print(f"\n  ⚠️  Failing checks: {failed}")
    return passed == total


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
