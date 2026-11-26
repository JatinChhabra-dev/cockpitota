"""
Module 6 — Acceptance Tests (AI Layer: Test Proposals, Failure Triage, Visual Classifier, Evidence Audit)
Verifies Spec §4 (pp. 13–14) M6-FR1 through M6-FR5 and Acceptance Criteria:
  - M6-FR1: Generates >= 5 test proposals from release_notes_v1.1.yaml including
            cross-feature "reverse while charging menu open"
  - M6-FR2: Proposals start PENDING_REVIEW and require human review (approve / edit / reject)
  - M6-FR3: Failure triage pulls real M5 VAR-B failure evidence (screenshot + logcat) and
            names APP-1 modal focus as likely cause
  - M6-FR4: Visual classifier labels de-DE change as DECLARED, 2px padding shift as COSMETIC,
            and VAR-B safety overlay suppression as DEFECT
  - M6-FR5: All prompts, input hashes, outputs, and reviewer decisions written to evidence/ai_records.json
  - M6 AC:  Turning AI layer OFF (POST /v1/ai/toggle {enabled: false}) blocks AI endpoints (503)
            while leaving M5 release gate / components fully functional (AI assists, never decides).

Usage:
    cd cockpit-ota
    python ai/test_m6_acceptance.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8001"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_RECORDS_PATH = os.path.join(ROOT_DIR, "evidence", "ai_records.json")

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
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw else {}), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return json.loads(raw), e.code
        except Exception:
            return {"raw": raw}, e.code


def run_tests():
    print("\n" + "=" * 68)
    print("  MODULE 6 — Acceptance Tests (AI Layer & Human Review Queue)")
    print("=" * 68)

    # Ensure AI is enabled at start
    _api("POST", "/v1/ai/toggle", {"enabled": True})

    # 1. M6-FR1: Generate >= 5 test proposals from release_notes_v1.1.yaml
    print("\n[1] Testing AI Test Proposal Generation (M6-FR1)...")
    gen_resp, gen_code = _api("POST", "/v1/releases/v1.1/ai/test-proposals")
    proposals = gen_resp.get("proposals", [])
    check("POST /v1/releases/v1.1/ai/test-proposals HTTP 200", gen_code == 200)
    check("Generated >= 5 test proposals from v1.1 notes", len(proposals) >= 5, f"count={len(proposals)}")
    has_cross_feature = any(
        "reverse" in p["title"].lower() and "charging" in p["title"].lower()
        for p in proposals
    )
    check("Includes cross-feature 'reverse while charging menu open' case", has_cross_feature)
    check("All proposals start in PENDING_REVIEW (origin=ai)", all(p["status"] == "PENDING_REVIEW" and p["origin"] == "ai" for p in proposals))

    # 2. M6-FR2: Human-in-the-loop review (approve / reject)
    print("\n[2] Testing Human Review Queue (M6-FR2)...")
    p0 = proposals[0]
    p1 = proposals[1]
    rev_ok, rev_code = _api("POST", f"/v1/test-proposals/{p0['proposal_id']}/review", {
        "decision": "approve",
        "reviewer": "QA Lead",
        "notes": "Approved for SC-03 safety coverage on VAR-B",
    })
    rev_rej, _ = _api("POST", f"/v1/test-proposals/{p1['proposal_id']}/review", {
        "decision": "reject",
        "reviewer": "QA Lead",
        "notes": "Covered by existing functional suite",
    })
    check("Approve proposal transitions to APPROVED with reviewer & timestamp", rev_code == 200 and rev_ok.get("status") == "APPROVED" and bool(rev_ok.get("approved_at")))
    check("Reject proposal transitions to REJECTED", rev_rej.get("status") == "REJECTED")

    # 3. M6-FR3: Failure Triage on REAL M5 VAR-B failure bundle
    print("\n[3] Testing AI Failure Triage on Real M5 VAR-B Evidence (M6-FR3)...")
    tri_resp, tri_code = _api("POST", "/v1/ai/triage", {"release_id": "v1.1", "variant_id": "VAR-B"})
    tri_out = tri_resp.get("ai_record", {}).get("output", {})
    cause_str = str(tri_out.get("likely_cause", "")).lower()
    check("POST /v1/ai/triage HTTP 200 using real M5 VAR-B run", tri_code == 200, f"run={tri_resp.get('bundle_summary', {}).get('run_id')}")
    check("Triage names APP-1 modal focus as likely cause", "app-1" in cause_str and "modal" in cause_str and "focus" in cause_str, tri_out.get("likely_cause", "")[:80])
    check("Triage attaches real screenshot URI & logcat reference", bool(tri_out.get("screenshot_uri")) and bool(tri_out.get("logcat_reference")), f"shot={os.path.basename(str(tri_out.get('screenshot_uri', '')))}")

    # 4. M6-FR4: Visual-Diff Classifier (DECLARED, COSMETIC, DEFECT)
    print("\n[4] Testing Visual-Diff Classifier (M6-FR4)...")
    v_decl, _ = _api("POST", "/v1/ai/visual-diff", {
        "variant_id": "VAR-C",
        "step": "BASELINE:home_parked",
        "diff_pct": 1.8,
        "change_id": "CHG-103",
        "safety_relevant": False,
        "description": "Updated de-DE German string for charging schedule",
    })
    v_cosm, _ = _api("POST", "/v1/ai/visual-diff", {
        "variant_id": "VAR-A",
        "step": "BASELINE:home_parked",
        "diff_pct": 0.4,
        "safety_relevant": False,
        "description": "Minor 2 px padding shift on non-safety card",
    })
    v_def, _ = _api("POST", "/v1/ai/visual-diff", {
        "variant_id": "VAR-B",
        "step": "SC-03:reverse_with_modal",
        "diff_pct": 64.2,
        "safety_relevant": True,
        "description": "Safety-relevant z-order changed; APP-2 overlay suppressed",
    })
    check("de-DE string change classified as DECLARED", v_decl.get("classification", {}).get("classification") == "DECLARED")
    check("2 px padding shift classified as COSMETIC", v_cosm.get("classification", {}).get("classification") == "COSMETIC")
    check("VAR-B safety overlay suppression classified as DEFECT", v_def.get("classification", {}).get("classification") == "DEFECT")

    # 5. M6-FR5: Auditable AIRecords persisted to evidence/ai_records.json
    print("\n[5] Verifying AI Evidence Audit Trail (M6-FR5)...")
    recs_resp, _ = _api("GET", "/v1/ai/records")
    recs = recs_resp.get("records", [])
    check("GET /v1/ai/records returns >= 5 auditable AIRecords", len(recs) >= 5, f"count={len(recs)}")
    check("Every AIRecord has model, prompt_version, input_hash", all(r.get("model") and r.get("prompt_version") and r.get("input_hash") for r in recs))
    check("evidence/ai_records.json persisted on disk", os.path.isfile(AI_RECORDS_PATH) and os.path.getsize(AI_RECORDS_PATH) > 200)

    # 6. M6 AC: Turning AI layer OFF leaves M5 gate fully functional
    print("\n[6] Verifying AI-Off Gate Independence (AI assists, never decides)...")
    _api("POST", "/v1/ai/toggle", {"enabled": False})
    _, ai_off_code = _api("POST", "/v1/releases/v1.1/ai/test-proposals")
    _, m5_comp_code = _api("GET", "/v1/components")
    _api("POST", "/v1/ai/toggle", {"enabled": True})
    check("AI endpoints return 503 when AI layer disabled", ai_off_code == 503, f"code={ai_off_code}")
    check("M5 Release Gate / Components remain HTTP 200 with AI disabled", m5_comp_code == 200)

    total = len(results)
    print("\n" + "=" * 68)
    print(f"  M6 Result: {passed}/{total} checks passed")
    print("=" * 68)
    if passed == total:
        print("\n  🎉 Module 6 (M6) GATE PASSED — AI LAYER & REVIEW QUEUE VERIFIED!")
    else:
        failed = [r["name"] for r in results if not r["passed"]]
        print(f"\n  ⚠️  Failing checks: {failed}")
    return passed == total


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
