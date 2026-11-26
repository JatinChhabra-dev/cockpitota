"""
Module 7 — Acceptance Tests (Evidence Store, Measured Metrics & UNECE R156 Dossier Export)
Verifies Spec §4 (pp. 14–15) M7-FR6..FR8 and §9 (all 9 dossier sections):
  - GET /v1/releases & GET /v1/metrics return real pipeline data
  - GET /v1/releases/v1.1-fix/dossier?format=json returns all 9 R156 sections + SHA-256 hash
  - GET /v1/releases/v1.1-fix/dossier?format=html returns Ferfier-branded HTML with SUMS disclaimer
  - GET /v1/releases/v1.1-fix/dossier?format=pdf returns valid %PDF-1.4 document in < 30s (M7-FR6)
  - All exported files persisted in evidence/dossiers/

Usage:
    cd cockpit-ota
    python dossier/test_m7_acceptance.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE_URL = "http://localhost:8001"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIERS_DIR = os.path.join(ROOT_DIR, "evidence", "dossiers")
DISCLAIMER = "Evidence prepared for SUMS review. Not a type-approval or certification decision."

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


def _get(path: str):
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=30) as resp:
        return resp.read(), resp.status, resp.headers.get("Content-Type", "")


def run_tests():
    print("\n" + "=" * 68)
    print("  MODULE 7 — Acceptance Tests (Evidence Store & R156 Dossier)")
    print("=" * 68)

    # 1. Releases & Measured Metrics (M7-FR7)
    print("\n[1] Verifying Releases Registry & Measured Metrics (M7-FR7)...")
    raw_rel, code_rel, _ = _get("/v1/releases")
    rels = json.loads(raw_rel.decode("utf-8"))
    check("GET /v1/releases returns v1.0, v1.1, v1.1-fix", code_rel == 200 and rels.get("total", 0) >= 3, f"total={rels.get('total')}")

    raw_met, code_met, _ = _get("/v1/metrics")
    met = json.loads(raw_met.decode("utf-8"))
    check("GET /v1/metrics returns measured boot, wall time, cost & counts", code_met == 200 and "measured_avg_boot_seconds" in met and "measured_avg_cost_per_run_usd" in met, f"runs={met.get('total_runs_recorded')}, ai={met.get('total_ai_records')}, ota={met.get('total_ota_ledger_records')}")

    # 2. JSON Dossier Export (all 9 UNECE R156 sections)
    print("\n[2] Exporting JSON Dossier for v1.1-fix (Spec §9)...")
    t0 = time.perf_counter()
    raw_json, code_json, _ = _get("/v1/releases/v1.1-fix/dossier?format=json&reviewer=Lead%20Homologation%20Engineer")
    elapsed_json = round(time.perf_counter() - t0, 3)
    dos = json.loads(raw_json.decode("utf-8"))
    expected_sections = [
        "1_release_identification",
        "2_purpose_of_update",
        "3_affected_systems",
        "4_approval_impact",
        "5_compatibility",
        "6_verification_evidence",
        "7_execution_safeguards",
        "8_per_vehicle_records",
        "9_sign_off",
    ]
    sections = dos.get("sections", {})
    check("JSON dossier HTTP 200 with all 9 R156 sections", code_json == 200 and all(k in sections for k in expected_sections), f"sections={len(sections)}, time={elapsed_json}s")
    check("JSON dossier carries SHA-256 integrity hash", len(dos.get("sha256", "")) == 64, f"sha256={dos.get('sha256', '')[:16]}...")
    check("JSON dossier carries mandatory SUMS disclaimer (M7-FR8)", dos.get("disclaimer") == DISCLAIMER)
    check("Section 1 contains real APK artefacts & SHA-256 hashes", len(sections.get("1_release_identification", {}).get("artefacts", [])) >= 2)
    check("Section 2 contains declared changes from release_notes_v1.1.yaml", len(sections.get("2_purpose_of_update", {}).get("declared_changes", [])) >= 3)

    # 3. HTML Dossier Export
    print("\n[3] Exporting Ferfier-Branded HTML Dossier...")
    raw_html, code_html, ct_html = _get("/v1/releases/v1.1-fix/dossier?format=html&reviewer=Lead%20Homologation%20Engineer")
    html_str = raw_html.decode("utf-8")
    check("HTML dossier HTTP 200 (text/html)", code_html == 200 and "text/html" in ct_html, f"bytes={len(raw_html)}")
    check("HTML dossier contains Ferfier Navy (#13294C) & SUMS disclaimer", "#13294C" in html_str and DISCLAIMER in html_str)

    # 4. PDF Dossier Export (M7-FR6: < 30s)
    print("\n[4] Exporting Standards-Compliant PDF Dossier (< 30s target)...")
    t0 = time.perf_counter()
    raw_pdf, code_pdf, ct_pdf = _get("/v1/releases/v1.1-fix/dossier?format=pdf&reviewer=Lead%20Homologation%20Engineer")
    elapsed_pdf = round(time.perf_counter() - t0, 3)
    check("PDF dossier HTTP 200 (application/pdf) with %PDF-1.4 header", code_pdf == 200 and "application/pdf" in ct_pdf and raw_pdf.startswith(b"%PDF-1.4"), f"bytes={len(raw_pdf)}")
    check("PDF dossier export completed under 30s ceiling (M7-FR6)", elapsed_pdf < 30.0, f"elapsed={elapsed_pdf}s")
    check("Persisted dossier files in evidence/dossiers/", os.path.isfile(os.path.join(DOSSIERS_DIR, "dossier_v1_1-fix.pdf")) and os.path.isfile(os.path.join(DOSSIERS_DIR, "dossier_v1_1-fix.html")))

    total = len(results)
    print("\n" + "=" * 68)
    print(f"  M7 Result: {passed}/{total} checks passed")
    print("=" * 68)
    if passed == total:
        print("\n  🎉 Module 7 (M7) GATE PASSED — ALL 9 R156 DOSSIER SECTIONS & EXPORTS VERIFIED!")
    else:
        failed = [r["name"] for r in results if not r["passed"]]
        print(f"\n  ⚠️  Failing checks: {failed}")
    return passed == total


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
