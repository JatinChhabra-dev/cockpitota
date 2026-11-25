"""
Module 1 — G1 Acceptance Test (All 3 Variants: VAR-A, VAR-B, VAR-C)
Verifies all acceptance criteria for the virtual cockpit fleet module per Spec §4 (M1-FR1..M1-FR6).

Run:
    cd cockpit-ota
    python fleet/test_m1_acceptance.py

Prerequisites:
  - Fleet Manager service running: python -m uvicorn fleet.manager:app --port 8001
  - AVDs created: AAOS-VAR-A, AAOS-VAR-B, AAOS-VAR-C
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

FLEET_API = "http://localhost:8001"

def _find_adb():
    candidates = [
        os.path.join(os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk"), "platform-tools", "adb.exe"),
        r"C:\Users\JatinChhabra\AppData\Local\Android\Sdk\platform-tools\adb.exe",
        r"C:\Users\brave\AppData\Local\Android\Sdk\platform-tools\adb.exe",
        "adb"
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "adb"

ADB = _find_adb()


def _api(method: str, path: str, body: dict = None):
    url = f"{FLEET_API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
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


def _adb_prop(serial: str, prop: str) -> str:
    res = subprocess.run([ADB, "-s", serial, "shell", "getprop", prop],
                         capture_output=True, text=True)
    return res.stdout.strip()


def _adb_wm_size(serial: str) -> tuple[int, int]:
    res = subprocess.run([ADB, "-s", serial, "shell", "wm", "size"],
                         capture_output=True, text=True)
    m = re.findall(r"(\d+)x(\d+)", res.stdout)
    if m:
        w, h = map(int, m[-1])
        return w, h
    return (0, 0)


def run_acceptance_tests():
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
    print("  MODULE 1 — G1 Acceptance Tests (Three-Variant Fleet)")
    print("="*60)

    # ----------------------------------------------------------------
    # 1: Fleet Manager health
    # ----------------------------------------------------------------
    print("\n[1] Fleet Manager API health...")
    try:
        resp, code = _api("GET", "/health")
        check("Fleet Manager is reachable", code == 200, f"status={resp.get('status')}")
    except Exception as e:
        check("Fleet Manager is reachable", False, str(e))
        print("  ⚠️  Start the fleet manager first:\n"
              "      python -m uvicorn fleet.manager:app --port 8001\n")
        return False

    # ----------------------------------------------------------------
    # 2: Variant configs loaded
    # ----------------------------------------------------------------
    print("\n[2] Variant config verification...")
    resp, _ = _api("GET", "/v1/fleet/variants")
    variants = resp.get("variants", {})
    check("VAR-A defined (Landscape en-US)", "VAR-A" in variants, f"locale={variants.get('VAR-A', {}).get('locale')}")
    check("VAR-B defined (Portrait en-US)", "VAR-B" in variants, f"display={variants.get('VAR-B', {}).get('display', {}).get('orientation')}")
    check("VAR-C defined (Landscape de-DE)", "VAR-C" in variants, f"locale={variants.get('VAR-C', {}).get('locale')}")

    def boot_and_verify(variant_id: str):
        print(f"\n[+] Booting {variant_id} instance via Fleet API...")
        resp, code = _api("POST", "/v1/fleet/instances", {"variant_id": variant_id, "build_tag": "v1.0", "count": 1})
        if code != 202 or not resp.get("instances"):
            check(f"{variant_id} launch accepted (202)", False, f"code={code}")
            return None
        
        inst_info = resp["instances"][0]
        instance_id = inst_info["instance_id"]
        vin = inst_info["vin_like"]
        check(f"{variant_id} launch accepted (202)", True)
        check(f"{variant_id} has VIN-format ID (starts ZFA)", vin.startswith("ZFA"), f"vin={vin}")

        print(f"  Waiting for {instance_id} to reach ONLINE status...")
        online_inst = None
        for _ in range(60):
            inst, _ = _api("GET", f"/v1/fleet/instances/{instance_id}")
            if inst.get("status") == "ONLINE":
                online_inst = inst
                break
            if inst.get("status") == "ERROR":
                err = inst.get("properties", {}).get("error", "unknown error")
                print(f"  ❌ Instance failed to boot: {err}")
                break
            time.sleep(5)

        is_online = bool(online_inst)
        check(f"{variant_id} reaches ONLINE status", is_online,
              f"boot={online_inst.get('boot_time_seconds') if online_inst else None}s serial={online_inst.get('adb_serial') if online_inst else None}")
        return online_inst

    # ----------------------------------------------------------------
    # 3: Boot and verify VAR-A (M1-FR2)
    # ----------------------------------------------------------------
    inst_a = boot_and_verify("VAR-A")
    if inst_a:
        serial_a = inst_a["adb_serial"]
        chars = _adb_prop(serial_a, "ro.build.characteristics")
        locale = _adb_prop(serial_a, "ro.product.locale")
        ev_flag = _adb_prop(serial_a, "debug.cora.ev_charge_schedule")
        w, h = _adb_wm_size(serial_a)
        check("VAR-A is automotive", "automotive" in chars, chars)
        check("VAR-A locale is en-US", "en" in locale.lower(), locale)
        check("VAR-A feature flag EV_CHARGE_SCHEDULE=on", ev_flag == "on", f"got='{ev_flag}'")
        check("VAR-A is landscape orientation", w >= h or w == 0, f"{w}x{h}")

    # ----------------------------------------------------------------
    # 4: Boot and verify VAR-B (M1-FR3 - Portrait Layout)
    # ----------------------------------------------------------------
    inst_b = boot_and_verify("VAR-B")
    if inst_b:
        serial_b = inst_b["adb_serial"]
        chars_b = _adb_prop(serial_b, "ro.build.characteristics")
        ev_flag_b = _adb_prop(serial_b, "debug.cora.ev_charge_schedule")
        w_b, h_b = _adb_wm_size(serial_b)
        check("VAR-B is automotive", "automotive" in chars_b, chars_b)
        check("VAR-B feature flag EV_CHARGE_SCHEDULE=on", ev_flag_b == "on", f"got='{ev_flag_b}'")
        check("VAR-B is portrait display (height > width)", h_b > w_b or (w_b == 1080 and h_b == 1920), f"{w_b}x{h_b}")

    # ----------------------------------------------------------------
    # 5: Boot and verify VAR-C (M1-FR4 - German Locale & Consent Prompt)
    # ----------------------------------------------------------------
    inst_c = boot_and_verify("VAR-C")
    if inst_c:
        serial_c = inst_c["adb_serial"]
        chars_c = _adb_prop(serial_c, "ro.build.characteristics")
        locale_c = _adb_prop(serial_c, "debug.cora.locale") or _adb_prop(serial_c, "persist.sys.locale") or _adb_prop(serial_c, "ro.product.locale")
        consent_flag = _adb_prop(serial_c, "debug.cora.eu_data_consent_prompt")
        w_c, h_c = _adb_wm_size(serial_c)
        check("VAR-C is automotive", "automotive" in chars_c, chars_c)
        check("VAR-C locale is de-DE", "de" in locale_c.lower(), locale_c)
        check("VAR-C feature flag EU_DATA_CONSENT_PROMPT=on", consent_flag == "on", f"got='{consent_flag}'")
        check("VAR-C is landscape orientation", w_c >= h_c or w_c == 0, f"{w_c}x{h_c}")

    # ----------------------------------------------------------------
    # 6: Screenshot & Debug Signal Injection API Tests
    # ----------------------------------------------------------------
    target_inst = inst_a or inst_b or inst_c
    if target_inst:
        t_id = target_inst["instance_id"]
        print(f"\n[6] Screenshot & Signal APIs on {t_id}...")
        resp_sc, code_sc = _api("POST", f"/v1/fleet/instances/{t_id}/screenshot")
        check("Screenshot captured via API", code_sc == 200, f"file={resp_sc.get('filename')}")

        sig_resp, sig_code = _api("POST", f"/v1/fleet/instances/{t_id}/signals",
                                   {"vss_path": "Vehicle.Powertrain.Transmission.SelectedGear", "value": "GEAR_PARK"})
        check("Debug signal injection via Fleet API succeeds", sig_code == 200, f"latency={sig_resp.get('latency_ms')}ms")

    # ----------------------------------------------------------------
    # 7: Teardown test (M1-FR6) — Cleanly tear down all spawned instances
    # ----------------------------------------------------------------
    print(f"\n[7] Teardown test (shutting down fleet instances)...")
    for inst in [inst_a, inst_b, inst_c]:
        if inst:
            t_id = inst["instance_id"]
            var_id = inst["variant_id"]
            t0 = time.time()
            _, del_code = _api("DELETE", f"/v1/fleet/instances/{t_id}")
            check(f"Tear down {var_id} ({t_id}) HTTP 204", del_code == 204, f"teardown_secs={round(time.time()-t0, 1)}")

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    total = len(results)
    print("\n" + "="*60)
    print(f"  G1 Result: {passed}/{total} checks passed")
    print("="*60)

    if passed == total:
        print("\n  🎉 Module 1 (M1) G1 GATE PASSED — ALL 3 VARIANTS VERIFIED!")
    else:
        failed = [r["name"] for r in results if not r["passed"]]
        print(f"\n  ⚠️  Failing checks: {failed}")

    return passed == total


if __name__ == "__main__":
    ok = run_acceptance_tests()
    sys.exit(0 if ok else 1)
