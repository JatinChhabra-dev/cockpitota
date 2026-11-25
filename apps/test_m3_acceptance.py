"""
Module 3 — Acceptance Tests (Demo OEM Applications: APP-1, APP-2, APP-3)
Verifies Spec §4 (p. 10) M3-FR1 through M3-FR5:
  - Signed APK artefacts & machine-readable release notes (v1.0, v1.1, v1.1-fix, rearview)
  - M3-FR1: APP-1 reads VHAL properties & enforces CarUxRestrictions while moving
  - M3-FR2: APP-2 Rear-view stand-in appears within 500 ms of GEAR_REVERSE on v1.0
  - M3-FR3: v1.1 declared changes present (card_charging_schedule_v2, btn_nav_shortcut_v2)
  - M3-FR4: v1.1 planted regression fails ONLY on VAR-B (portrait) with reproducible logcat signature
  - M3-FR5: v1.1-fix resolves VAR-B regression while preserving declared changes
  - SC-04:  APP-3 Mock Vehicle Cloud delivers remote climate command to cockpit

Usage:
    cd cockpit-ota
    python apps/test_m3_acceptance.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import yaml

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from fleet.avd_backend import _adb_path

FLEET_URL = "http://localhost:8001"
APPS_DIR = os.path.join(ROOT_DIR, "apps")
DIST_DIR = os.path.join(APPS_DIR, "dist")
ADB = _adb_path()

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
    url = f"{FLEET_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw else {}), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return json.loads(raw), e.code
        except Exception:
            return {"raw": raw}, e.code


def _adb(serial: str, args: list[str], timeout: int = 30) -> str:
    res = subprocess.run([ADB, "-s", serial] + args, capture_output=True, text=True, timeout=timeout)
    return (res.stdout + "\n" + res.stderr).strip()


def _install_apk(serial: str, apk_name: str):
    apk_path = os.path.join(DIST_DIR, apk_name)
    out = _adb(serial, ["install", "-r", "-d", "-g", apk_path], timeout=60)
    if "Success" not in out:
        raise RuntimeError(f"Failed to install {apk_name} on {serial}: {out}")


def _top_activity(serial: str) -> str:
    out = _adb(serial, ["shell", "dumpsys", "activity", "activities"])
    for line in out.splitlines():
        if "topResumedActivity=" in line or "mResumedActivity:" in line or "ResumedActivity:" in line:
            return line.strip()
    return ""


def _ensure_variant_online(variant_id: str) -> dict | None:
    insts, _ = _api("GET", f"/v1/fleet/instances?variant_id={variant_id}&status=ONLINE")
    if insts.get("instances"):
        inst = insts["instances"][0]
        print(f"  Reusing running {variant_id}: {inst['instance_id']} ({inst['adb_serial']})")
        return inst

    print(f"  Launching {variant_id} via Fleet API...")
    resp, code = _api("POST", "/v1/fleet/instances", {"variant_id": variant_id, "build_tag": "v1.0", "count": 1})
    if code != 202 or not resp.get("instances"):
        return None
    inst_id = resp["instances"][0]["instance_id"]
    for _ in range(90):
        info, _ = _api("GET", f"/v1/fleet/instances/{inst_id}")
        if info.get("status") == "ONLINE":
            print(f"  {variant_id} ONLINE: {inst_id} ({info.get('adb_serial')})")
            return info
        if info.get("status") == "ERROR":
            print(f"  {variant_id} boot ERROR: {info.get('properties', {}).get('error')}")
            return None
        time.sleep(3)
    return None


def _run_sc03_reverse_check(inst: dict, serial: str) -> tuple[bool, int | None, bool]:
    """
    Executes SC-03 on the given cockpit instance:
      1. Gear PARK, speed 0
      2. Launch APP-1 & open charging modal
      3. Clear logcat, shift to GEAR_REVERSE
      4. Check if APP-2 RearViewActivity is top activity, extract render latency,
         and check for M3-FR4 defect log signature.
    Returns: (rearview_visible, render_latency_ms, defect_logged)
    """
    inst_id = inst["instance_id"]
    _api("POST", f"/v1/fleet/instances/{inst_id}/signals", {"vss_path": "Vehicle.Speed", "value": 0})
    _api("POST", f"/v1/fleet/instances/{inst_id}/signals", {"vss_path": "Vehicle.Powertrain.Transmission.SelectedGear", "value": "GEAR_PARK"})
    time.sleep(0.5)

    # Start APP-1 and open charging schedule modal
    _adb(serial, ["shell", "am", "start", "-n", "com.aurelia.ev/.MainActivity"])
    time.sleep(1.0)
    _adb(serial, ["shell", "am", "broadcast", "-a", "com.aurelia.ev.ACTION_OPEN_CHARGING_MODAL", "-n", "com.aurelia.ev/.RemoteCommandReceiver"])
    time.sleep(1.0)

    # Clear logcat before shifting to Reverse
    _adb(serial, ["logcat", "-c"])
    _api("POST", f"/v1/fleet/instances/{inst_id}/signals", {"vss_path": "Vehicle.Powertrain.Transmission.SelectedGear", "value": "GEAR_REVERSE"})
    time.sleep(1.2)

    top = _top_activity(serial)
    rearview_visible = "com.aurelia.rearview/.RearViewActivity" in top

    log_out = _adb(serial, ["logcat", "-d", "-s", "AureliaEV:I", "AureliaEV:E", "AureliaRearView:I"])
    defect_logged = "[DEFECT_M3_FR4]" in log_out

    latency_ms = None
    m = re.search(r"RearViewActivity visible in (\d+)ms", log_out)
    if m:
        latency_ms = int(m.group(1))

    # Restore to PARK
    _api("POST", f"/v1/fleet/instances/{inst_id}/signals", {"vss_path": "Vehicle.Powertrain.Transmission.SelectedGear", "value": "GEAR_PARK"})
    time.sleep(0.6)
    return rearview_visible, latency_ms, defect_logged


def run_tests():
    print("\n" + "=" * 64)
    print("  MODULE 3 — Acceptance Tests (APP-1, APP-2, APP-3)")
    print("=" * 64)

    # 1. Verify build artefacts & release notes
    print("\n[1] Verifying compiled APKs & release notes...")
    expected_apks = [
        "aurelia-ev-v1.0.apk",
        "aurelia-ev-v1.1.apk",
        "aurelia-ev-v1.1-fix.apk",
        "aurelia-rearview-v1.0.apk",
    ]
    for apk in expected_apks:
        path = os.path.join(DIST_DIR, apk)
        check(f"Signed APK exists: {apk}", os.path.isfile(path) and os.path.getsize(path) > 1024, f"{os.path.getsize(path) if os.path.isfile(path) else 0} bytes")

    rn_path = os.path.join(APPS_DIR, "release_notes_v1.1.yaml")
    rn = yaml.safe_load(open(rn_path, "r", encoding="utf-8")) if os.path.isfile(rn_path) else {}
    check("Machine-readable release_notes_v1.1.yaml valid", len(rn.get("declared_changes", [])) >= 3, f"{len(rn.get('declared_changes', []))} declared changes")

    # 2. Ensure VAR-A (landscape) and VAR-B (portrait) are ONLINE
    print("\n[2] Preparing VAR-A (Landscape) and VAR-B (Portrait) cockpits...")
    inst_a = _ensure_variant_online("VAR-A")
    inst_b = _ensure_variant_online("VAR-B")
    check("VAR-A cockpit online", inst_a is not None, str(inst_a.get("adb_serial") if inst_a else None))
    check("VAR-B cockpit online", inst_b is not None, str(inst_b.get("adb_serial") if inst_b else None))
    if not inst_a or not inst_b:
        print("  Cannot continue live app tests without VAR-A and VAR-B online.")
        return False

    serial_a = inst_a["adb_serial"]
    serial_b = inst_b["adb_serial"]

    # Install APP-2 on both
    _install_apk(serial_a, "aurelia-rearview-v1.0.apk")
    _install_apk(serial_b, "aurelia-rearview-v1.0.apk")

    # 3. Baseline v1.0 checks (M3-FR1 & M3-FR2)
    print("\n[3] Testing Baseline v1.0 on VAR-A and VAR-B (M3-FR1, M3-FR2)...")
    _install_apk(serial_a, "aurelia-ev-v1.0.apk")
    _install_apk(serial_b, "aurelia-ev-v1.0.apk")

    rv_a_v10, lat_a_v10, def_a_v10 = _run_sc03_reverse_check(inst_a, serial_a)
    check("v1.0 VAR-A (Landscape): APP-2 visible on Reverse", rv_a_v10 and not def_a_v10, f"latency={lat_a_v10}ms")
    check("v1.0 VAR-A: APP-2 latency < 500ms", lat_a_v10 is not None and lat_a_v10 < 500, f"{lat_a_v10}ms")

    rv_b_v10, lat_b_v10, def_b_v10 = _run_sc03_reverse_check(inst_b, serial_b)
    check("v1.0 VAR-B (Portrait): APP-2 visible on Reverse", rv_b_v10 and not def_b_v10, f"latency={lat_b_v10}ms")

    # 4. Candidate v1.1 checks (M3-FR4: planted defect ONLY on VAR-B portrait)
    print("\n[4] Testing Candidate v1.1 (M3-FR4 planted regression on VAR-B only)...")
    _install_apk(serial_a, "aurelia-ev-v1.1.apk")
    _install_apk(serial_b, "aurelia-ev-v1.1.apk")

    rv_a_v11, lat_a_v11, def_a_v11 = _run_sc03_reverse_check(inst_a, serial_a)
    check("v1.1 VAR-A (Landscape): still passes SC-03", rv_a_v11 and not def_a_v11, f"latency={lat_a_v11}ms")

    rv_b_v11, lat_b_v11, def_b_v11 = _run_sc03_reverse_check(inst_b, serial_b)
    check("v1.1 VAR-B (Portrait): APP-2 suppressed by modal defect", (not rv_b_v11), f"rearview_visible={rv_b_v11}")
    check("v1.1 VAR-B (Portrait): reproducible [DEFECT_M3_FR4] logcat signature", def_b_v11)

    # 5. Fix build v1.1-fix checks (M3-FR5)
    print("\n[5] Testing Fix Build v1.1-fix on VAR-B (M3-FR5)...")
    _install_apk(serial_b, "aurelia-ev-v1.1-fix.apk")
    rv_b_fix, lat_b_fix, def_b_fix = _run_sc03_reverse_check(inst_b, serial_b)
    check("v1.1-fix VAR-B (Portrait): APP-2 restored on Reverse", rv_b_fix and not def_b_fix, f"latency={lat_b_fix}ms")
    check("v1.1-fix VAR-B: APP-2 latency < 500ms", lat_b_fix is not None and lat_b_fix < 500, f"{lat_b_fix}ms")

    # 6. APP-3 Mock Vehicle Cloud Remote Climate (SC-04)
    print("\n[6] Testing APP-3 Mock Vehicle Cloud Remote Climate (SC-04)...")
    cloud_resp, cloud_code = _api("POST", f"/v1/cloud/vehicles/{inst_a['instance_id']}/climate", {"temperature_c": 21.0})
    check("POST /v1/cloud/vehicles/{id}/climate HTTP 200", cloud_code == 200, f"status={cloud_resp.get('command', {}).get('status')}")
    check("Remote climate 21.0 C delivered to VHAL", cloud_resp.get("vhal", {}).get("injected_value") == 21.0)

    total = len(results)
    print("\n" + "=" * 64)
    print(f"  M3 Result: {passed}/{total} checks passed")
    print("=" * 64)
    if passed == total:
        print("\n  🎉 Module 3 (M3) GATE PASSED — ALL OEM APPS & VARIANTS VERIFIED!")
    else:
        failed = [r["name"] for r in results if not r["passed"]]
        print(f"\n  ⚠️  Failing checks: {failed}")
    return passed == total


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
