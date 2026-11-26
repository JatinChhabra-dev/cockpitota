"""
Module 5 — Live Acceptance Tests (Test & Equivalence Engine + Release Gate)
Verifies Spec §4 (pp. 12–13) M5-FR1..FR8 and Acceptance Criteria on REAL AAOS emulators:
  1. Baseline v1.0 runs live on VAR-A (Landscape) & VAR-B (Portrait) -> all suites PASS
  2. Candidate v1.1 runs live on VAR-A & VAR-B:
       - VAR-A PASSES
       - VAR-B is BLOCKED (SC-03 safety z-order failure + UNEXPLAINED diff + RXSWIN-impact=True)
       - Overall release gate BLOCKS OTA (ota_eligible=False)
  3. Fix build v1.1-fix runs live on VAR-A & VAR-B:
       - Only DECLARED & COSMETIC differences (0 UNEXPLAINED)
       - Gate PASSES on both variants (ota_eligible=True)
  4. Undeclared string change check: mutating an undeclared UI node text produces
     UNEXPLAINED and BLOCKS the gate.

Usage:
    cd cockpit-ota
    python engine/test_m5_acceptance.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from engine.differ import build_equivalence_report
from engine.gate import release_gate
from engine.models import RunRecord

BASE_URL = "http://localhost:8001"
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


def _api(method: str, path: str, body: dict | None = None, timeout: int = 180):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw else {}), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return json.loads(raw), e.code
        except Exception:
            return {"raw": raw}, e.code


def _ensure_variant_online(variant_id: str) -> dict | None:
    insts, _ = _api("GET", f"/v1/fleet/instances?variant_id={variant_id}&status=ONLINE", timeout=15)
    if insts.get("instances"):
        inst = insts["instances"][0]
        print(f"  Reusing running {variant_id}: {inst['instance_id']} ({inst['adb_serial']})")
        return inst

    print(f"  Launching {variant_id} via Fleet API...")
    resp, code = _api("POST", "/v1/fleet/instances", {"variant_id": variant_id, "build_tag": "v1.0", "count": 1}, timeout=30)
    if code != 202 or not resp.get("instances"):
        return None
    inst_id = resp["instances"][0]["instance_id"]
    for _ in range(90):
        info, _ = _api("GET", f"/v1/fleet/instances/{inst_id}", timeout=15)
        if info.get("status") == "ONLINE":
            print(f"  {variant_id} ONLINE: {inst_id} ({info.get('adb_serial')})")
            return info
        if info.get("status") == "ERROR":
            print(f"  {variant_id} boot ERROR: {info.get('properties', {}).get('error')}")
            return None
        time.sleep(3)
    return None


def run_tests():
    print("\n" + "=" * 68)
    print("  MODULE 5 — Live Acceptance Tests (Equivalence Engine & Gate)")
    print("=" * 68)

    # 1. Verify Component Register & live VAR-A / VAR-B emulators
    print("\n[1] Checking Component Register & Preparing Live VAR-A + VAR-B...")
    comp_resp, comp_code = _api("GET", "/v1/components", timeout=15)
    check("GET /v1/components returns APP-1/2/3 register", comp_code == 200 and "APP-2" in comp_resp.get("components", {}))

    inst_a = _ensure_variant_online("VAR-A")
    inst_b = _ensure_variant_online("VAR-B")
    check("VAR-A live cockpit online", inst_a is not None, str(inst_a.get("adb_serial") if inst_a else None))
    check("VAR-B live cockpit online", inst_b is not None, str(inst_b.get("adb_serial") if inst_b else None))
    if not inst_a or not inst_b:
        return False

    variants = ["VAR-A", "VAR-B"]
    scenarios = ["SC-01", "SC-02", "SC-03", "SC-04"]

    # 2. Run Baseline v1.0 live in parallel on VAR-A and VAR-B
    print("\n[2] Running Baseline v1.0 live on VAR-A & VAR-B (SC-01..SC-04)...")
    r10, c10 = _api("POST", "/v1/runs", {"release_id": "v1.0", "variants": variants, "scenarios": scenarios})
    check("POST /v1/runs (v1.0) completed HTTP 200", c10 == 200 and r10.get("total") == 2, f"runs={r10.get('total')}")
    v10_all_pass = all(
        all(res["status"] == "pass" for res in run["results"])
        for run in r10.get("runs", [])
    )
    check("Baseline v1.0 passes all suites on VAR-A & VAR-B", v10_all_pass)
    v10_has_evidence = all(
        os.path.isfile(run.get("junit_xml_path", "")) and os.path.isfile(run.get("trace_json_path", ""))
        for run in r10.get("runs", [])
    )
    check("Baseline v1.0 persisted JUnit XML + JSON trace bundles", v10_has_evidence)

    # 3. Run Candidate v1.1 live on VAR-A & VAR-B -> Gate MUST BLOCK on VAR-B only!
    print("\n[3] Running Candidate v1.1 live on VAR-A & VAR-B (Expect VAR-B BLOCK)...")
    r11, c11 = _api("POST", "/v1/runs", {"release_id": "v1.1", "variants": variants, "scenarios": scenarios})
    check("POST /v1/runs (v1.1) completed HTTP 200", c11 == 200 and r11.get("total") == 2)

    eq11, eq11_code = _api("GET", "/v1/releases/v1.1/equivalence?baseline=v1.0")
    check("GET /v1/releases/v1.1/equivalence returns HTTP 200", eq11_code == 200, f"summary={eq11.get('summary')}")
    check("v1.1 equivalence flags UNEXPLAINED difference(s)", eq11.get("summary", {}).get("unexplained", 0) > 0, f"unexplained={eq11.get('summary', {}).get('unexplained')}")

    gate11, gate11_code = _api("POST", "/v1/releases/v1.1/gate?baseline=v1.0")
    by_var_11 = {v["variant_id"]: v for v in gate11.get("variants", [])}
    check("Gate v1.1: VAR-A (Landscape) PASSES", by_var_11.get("VAR-A", {}).get("outcome") == "PASS", str(by_var_11.get("VAR-A", {}).get("reasons")))
    check("Gate v1.1: VAR-B (Portrait) BLOCKED", by_var_11.get("VAR-B", {}).get("outcome") == "BLOCK", str(by_var_11.get("VAR-B", {}).get("reasons")))
    check("Gate v1.1: RXSWIN-impact flag set on VAR-B (APP-2 safety)", by_var_11.get("VAR-B", {}).get("rxswin_impact") is True, str(by_var_11.get("VAR-B", {}).get("rxswin_components")))
    check("Gate v1.1: Overall release BLOCKED (ota_eligible=False)", gate11.get("overall_outcome") == "BLOCK" and gate11.get("ota_eligible") is False)

    # 4. Run Fix Build v1.1-fix live on VAR-A & VAR-B -> Gate MUST PASS!
    print("\n[4] Running Fix Build v1.1-fix live on VAR-A & VAR-B (Expect PASS)...")
    rfix, cfix = _api("POST", "/v1/runs", {"release_id": "v1.1-fix", "variants": variants, "scenarios": scenarios})
    check("POST /v1/runs (v1.1-fix) completed HTTP 200", cfix == 200 and rfix.get("total") == 2)

    eqfix, eqfix_code = _api("GET", "/v1/releases/v1.1-fix/equivalence?baseline=v1.0")
    check("GET /v1/releases/v1.1-fix/equivalence returns HTTP 200", eqfix_code == 200, f"summary={eqfix.get('summary')}")
    check("v1.1-fix has DECLARED changes & ZERO UNEXPLAINED diffs",
          eqfix.get("summary", {}).get("declared", 0) > 0 and eqfix.get("summary", {}).get("unexplained", -1) == 0,
          f"summary={eqfix.get('summary')}")

    gatefix, _ = _api("POST", "/v1/releases/v1.1-fix/gate?baseline=v1.0")
    check("Gate v1.1-fix: Overall PASS (ota_eligible=True)", gatefix.get("overall_outcome") == "PASS" and gatefix.get("ota_eligible") is True, f"outcome={gatefix.get('overall_outcome')}")

    # 5. Undeclared string change check (Spec M5 AC #3)
    print("\n[5] Verifying Undeclared String Change Detection (Spec M5 AC #3)...")
    base_map = {r["variant_id"]: RunRecord(**r) for r in r10["runs"]}
    mut_map = {r["variant_id"]: RunRecord(**copy.deepcopy(r)) for r in rfix["runs"]}
    # Mutate an UNDECLARED UI node (txt_powertrain_badge) on VAR-A home trace
    for t in mut_map["VAR-A"].traces:
        if "com.aurelia.ev:id/txt_powertrain_badge" in t.ui_nodes:
            t.ui_nodes["com.aurelia.ev:id/txt_powertrain_badge"].text = "UNDECLARED_STRING_MUTATION"
            break
    mut_eq = build_equivalence_report(base_map, mut_map, "v1.0", "v1.1-undeclared-test")
    mut_gate = release_gate.evaluate("v1.1-undeclared-test", "v1.0", mut_map, mut_eq)
    check("Undeclared string change produces UNEXPLAINED diff & BLOCKS gate",
          mut_eq.summary.get("unexplained", 0) > 0 and mut_gate["overall_outcome"] == "BLOCK",
          f"unexplained={mut_eq.summary.get('unexplained')}, outcome={mut_gate['overall_outcome']}")

    total = len(results)
    print("\n" + "=" * 68)
    print(f"  M5 Result: {passed}/{total} checks passed")
    print("=" * 68)
    if passed == total:
        print("\n  🎉 Module 5 (M5) GATE PASSED — EQUIVALENCE ENGINE & RELEASE GATE VERIFIED!")
    else:
        failed = [r["name"] for r in results if not r["passed"]]
        print(f"\n  ⚠️  Failing checks: {failed}")
    return passed == total


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
