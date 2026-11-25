"""
Module 2 — G2 Acceptance Tests (Vehicle Signal Simulator)
Verifies:
1. Scenario catalogue integrity (SC-01 through SC-05).
2. VSS to VHAL mapping completeness.
3. Deterministic scenario replay & trace emission.
4. Latency ceiling (< 500ms for safety reverse gear).
5. CAN CSV import to scenario YAML (M2-FR5).
6. Scenarios REST API endpoints (/v1/scenarios).

Run:
    cd cockpit-ota
    python signals/test_m2_acceptance.py
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

# Ensure project root in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, root_dir)

from signals.injector import VhalInjector
from signals.replay import ScenarioReplayController
from signals.can_importer import import_can_csv_to_scenario

FLEET_API = "http://localhost:8001"

def _api(method: str, path: str, body: dict = None):
    url = f"{FLEET_API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            text = content.decode("utf-8", errors="ignore") if content else ""
            try:
                return json.loads(text) if text else {}, resp.status
            except Exception:
                return {"raw": text}, resp.status
    except urllib.error.HTTPError as e:
        content = e.read()
        text = content.decode("utf-8", errors="ignore") if content else ""
        try:
            return json.loads(text) if text else {}, e.code
        except Exception:
            return {"raw": text}, e.code
    except Exception as e:
        return {"error": str(e)}, 500

def run_m2_acceptance_tests():
    results = []
    passed = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed
        status = "PASS ✅" if ok else "FAIL ❌"
        results.append({"name": name, "passed": ok, "detail": detail})
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        if ok:
            passed += 1

    print("\n" + "="*60)
    print("  MODULE 2 — G2 Acceptance Tests (Signal Simulator)")
    print("="*60)

    # ----------------------------------------------------------------
    # 1. Scenario Catalogue Verification
    # ----------------------------------------------------------------
    print("\n[1] Verifying Scenario Catalogue (SC-01 .. SC-05)...")
    scenarios_dir = os.path.join(root_dir, "signals", "scenarios")
    expected_scenarios = ["SC-01", "SC-02", "SC-03", "SC-04", "SC-05"]
    
    found_scenarios = []
    for sc in expected_scenarios:
        # Check files
        matched = [f for f in os.listdir(scenarios_dir) if sc.lower().replace("-", "") in f.lower().replace("-", "").replace("_", "")]
        is_present = len(matched) > 0
        if is_present:
            found_scenarios.append(sc)
        check(f"Scenario {sc} specification exists", is_present, matched[0] if is_present else "missing")

    # ----------------------------------------------------------------
    # 2. VSS -> VHAL Mapping Verification
    # ----------------------------------------------------------------
    print("\n[2] Verifying VSS to VHAL Mapping Integrity...")
    from fleet.avd_backend import _adb_path
    adb_bin = _adb_path()
    injector = VhalInjector(adb_path=adb_bin)
    mappings = injector.mappings
    
    required_vss = [
        "Vehicle.Speed",
        "Vehicle.Powertrain.Transmission.SelectedGear",
        "Vehicle.Powertrain.Transmission.CurrentGear",
        "Vehicle.Chassis.ParkingBrake.IsEngaged",
        "Vehicle.LowVoltageSystemState",
        "Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed",
        "Vehicle.Powertrain.TractionBattery.Charging.ChargePortFlap",
        "Vehicle.Powertrain.TractionBattery.Charging.IsChargingCableConnected",
        "Vehicle.Cabin.HVAC.Station.Row1.Driver.Temperature"
    ]
    
    all_mapped = all(v in mappings for v in required_vss)
    check("All 9 required VSS signals mapped to VHAL", all_mapped, f"{len(mappings)} mappings loaded")
    
    # ----------------------------------------------------------------
    # 3. CAN CSV Importer Test (M2-FR5)
    # ----------------------------------------------------------------
    print("\n[3] Testing CAN Log Importer (M2-FR5)...")
    sample_csv = os.path.join(root_dir, "signals", "sample_can_log.csv")
    out_yaml = os.path.join(root_dir, "signals", "scenarios", "imported_can_test.yaml")
    
    imported = import_can_csv_to_scenario(sample_csv, out_yaml, scenario_id="SC-CAN-TEST")
    check("CAN CSV imported into Scenario YAML", os.path.isfile(out_yaml), f"{len(imported.get('steps', []))} steps generated")
    check("CAN GearPosition mapped to VSS SelectedGear", any(s.get("signal") == "Vehicle.Powertrain.Transmission.SelectedGear" for s in imported["steps"]))
    check("CAN VehicleSpeed mapped to VSS Vehicle.Speed", any(s.get("signal") == "Vehicle.Speed" for s in imported["steps"]))

    # ----------------------------------------------------------------
    # 4. Live Cockpit Deterministic Replay (SC-03 Safety & Timing)
    # ----------------------------------------------------------------
    print("\n[4] Ensuring active AAOS instance for live replay...")
    # Check if any instance is already ONLINE
    active_inst_id = None
    serial = None
    
    inst_list, _ = _api("GET", "/v1/fleet/instances?status=ONLINE")
    if inst_list.get("instances"):
        active_inst = inst_list["instances"][0]
        active_inst_id = active_inst["instance_id"]
        serial = active_inst.get("adb_serial")
        print(f"  Using existing ONLINE instance: {active_inst_id} ({serial})")
    else:
        print("  No active instance found. Requesting launch of VAR-A via Fleet API...")
        launch_res, code = _api("POST", "/v1/fleet/instances", {"variant_id": "VAR-A", "build_tag": "v1.0", "count": 1})
        if code == 202 and launch_res.get("instances"):
            active_inst_id = launch_res["instances"][0]["instance_id"]
            print(f"  Waiting for {active_inst_id} to boot...")
            for _ in range(60):
                chk, _ = _api("GET", f"/v1/fleet/instances/{active_inst_id}")
                if chk.get("status") == "ONLINE":
                    serial = chk.get("adb_serial")
                    print(f"  Instance {active_inst_id} is ONLINE on {serial}!")
                    break
                time.sleep(3)

    check("Cockpit instance ready for signal replay", bool(serial), f"serial={serial}")

    print("\n  Executing SC-03 (Reverse Gear Latency Check)...")
    injector.serial = serial
    controller = ScenarioReplayController(injector=injector, speed_factor=3.0, instance_id=active_inst_id or "inst-001")
    sc03_file = os.path.join(scenarios_dir, "sc03_reverse_menu_open.yaml")
    
    trace_sc03 = controller.replay(sc03_file)
    check("SC-03 Replay produced trace events", len(trace_sc03) >= 3, f"steps={len(trace_sc03)}")
    
    # Check reverse latency
    reverse_step = next((t for t in trace_sc03 if t.get("signal") == "Vehicle.Powertrain.Transmission.SelectedGear" and t.get("injected_value") == 2), None)
    if reverse_step:
        lat = reverse_step.get("latency_ms", 999)
        check("Reverse Gear injection latency < 500ms ceiling", lat < 500, f"measured={lat}ms")
    else:
        check("Reverse Gear injection latency < 500ms ceiling", False, "Reverse step not found in trace")

    # ----------------------------------------------------------------
    # 5. Live Cockpit Replay: SC-02 (Park & Charge)
    # ----------------------------------------------------------------
    print("\n[5] Live Replay on Cockpit: SC-02 (Park & Charge)...")
    sc02_file = os.path.join(scenarios_dir, "sc02_park_and_charge.yaml")
    controller_fast = ScenarioReplayController(injector=injector, speed_factor=5.0)
    trace_sc02 = controller_fast.replay(sc02_file)
    check("SC-02 Park & Charge executed", len(trace_sc02) >= 5, f"steps={len(trace_sc02)}")

    # ----------------------------------------------------------------
    # 6. REST API Endpoints Verification (/v1/scenarios)
    # ----------------------------------------------------------------
    print("\n[6] Testing Scenarios REST API Endpoints...")
    scenarios_list, code_list = _api("GET", "/v1/scenarios")
    check("GET /v1/scenarios returns HTTP 200", code_list == 200, f"found={len(scenarios_list)} scenarios")
    
    sc01_detail, code_get = _api("GET", "/v1/scenarios/SC-01")
    check("GET /v1/scenarios/SC-01 returns specification", code_get == 200, f"name={sc01_detail.get('name')}")

    # Replay via REST
    print("  Testing POST /v1/scenarios/SC-01/replay via REST...")
    replay_resp, code_replay = _api("POST", "/v1/scenarios/SC-01/replay", {
        "instance_id": active_inst_id or "inst-local-test",
        "speed_factor": 5.0,
        "adb_serial": serial
    })
    if code_replay != 200:
        print(f"  [DEBUG] POST replay returned code={code_replay}, body={replay_resp}")
    check("POST /v1/scenarios/SC-01/replay returns HTTP 200", code_replay == 200, f"status={replay_resp.get('status')}")
    check("Replay trace returned via REST", len(replay_resp.get("trace", [])) > 0, f"steps={len(replay_resp.get('trace', []))}")

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    total = len(results)
    print("\n" + "="*60)
    print(f"  G2 Result: {passed}/{total} checks passed")
    print("="*60)

    if passed == total:
        print("\n  🎉 Module 2 (M2) G2 GATE PASSED — ready for Module 3 (M3 Demo Apps)")
    else:
        failed = [r["name"] for r in results if not r["passed"]]
        print(f"\n  ⚠️  Failing checks: {failed}")

    return passed == total

if __name__ == "__main__":
    ok = run_m2_acceptance_tests()
    sys.exit(0 if ok else 1)
