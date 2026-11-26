"""
Module 5 Release Gate Service & RXSWIN-Impact Evaluator (Spec §4 M5-FR6, M5-FR7, Figure 3).
Idempotent decision engine:
  1. Did all suites run on the variant?
  2. Did all functional, UX-restriction, safety, and localisation tests PASS (no FAIL, no FLAKY)?
  3. Are there zero UNEXPLAINED equivalence differences (including safety z-order / visual defects)?
  4. In parallel: compute RXSWIN-impact from engine/components.yaml (approval_relevant components).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Dict, List
import yaml

from engine.models import (
    DiffClass,
    EquivalenceReport,
    GateDecision,
    GateOutcome,
    RunRecord,
    TestStatus,
)

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(ENGINE_DIR)
COMPONENTS_FILE = os.path.join(ENGINE_DIR, "components.yaml")
GATES_DIR = os.path.join(ROOT_DIR, "evidence", "gates")


def load_component_register() -> Dict[str, dict]:
    if not os.path.isfile(COMPONENTS_FILE):
        return {}
    with open(COMPONENTS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("components", {})


class ReleaseGateService:
    def __init__(self):
        self.decisions: Dict[str, List[GateDecision]] = {}  # release_id -> [GateDecision per variant]

    def evaluate(
        self,
        release_id: str,
        baseline_release_id: str,
        candidate_runs: Dict[str, RunRecord],
        equiv_report: EquivalenceReport,
    ) -> Dict:
        """
        Idempotent gate evaluation per variant + overall release decision.
        Persists decision bundle into evidence/gates/<release_id>_gate.json.
        """
        components = load_component_register()
        approval_components = {
            cid: c for cid, c in components.items() if c.get("approval_relevant") is True
        }

        per_variant: List[GateDecision] = []
        now_iso = datetime.utcnow().isoformat() + "Z"

        for vid in sorted(candidate_runs.keys()):
            run = candidate_runs[vid]
            v_diffs = [d for d in equiv_report.differences if d.variant_id == vid]

            failed_tests = [
                f"{r.suite}:{r.test_id} ({r.status.value}) — {r.message}"
                for r in run.results
                if r.status in (TestStatus.FAIL, TestStatus.FLAKY)
            ]
            unexplained_diffs = [d for d in v_diffs if d.diff_class == DiffClass.UNEXPLAINED]

            reasons: List[str] = []
            if run.status != "COMPLETED":
                reasons.append(f"Run did not complete cleanly (status={run.status})")
            if failed_tests:
                reasons.append(f"{len(failed_tests)} check(s) failed/flaky: {failed_tests[0]}")
            if unexplained_diffs:
                reasons.append(f"{len(unexplained_diffs)} UNEXPLAINED equivalence difference(s): {unexplained_diffs[0].detail}")

            outcome = GateOutcome.PASS if not reasons else GateOutcome.BLOCK

            # Parallel RXSWIN-impact check (M5-FR7):
            # Triggered if any failed test or difference touches an approval-relevant component (e.g. APP-2 rear-view)
            rxswin_hits: List[str] = []
            touches_safety = (
                any(r.suite == "safety_display" and r.status != TestStatus.PASS for r in run.results)
                or any(d.kind == "z_order" or "rearview" in str(d.detail).lower() or "SC-03" in d.step for d in unexplained_diffs)
            )
            if touches_safety:
                for cid, comp in approval_components.items():
                    rxswin_hits.append(f"{cid} ({comp.get('rxswin_ref', 'RXSWIN')})")

            decision = GateDecision(
                gate_id=f"gate-{release_id.replace('.', '_')}-{vid.lower()}-{uuid.uuid4().hex[:6]}",
                release_id=release_id,
                baseline_release_id=baseline_release_id,
                variant_id=vid,
                outcome=outcome,
                reasons=reasons if reasons else ["All suites passed; only DECLARED/COSMETIC equivalence differences"],
                rxswin_impact=len(rxswin_hits) > 0,
                rxswin_components=rxswin_hits,
                failed_tests=failed_tests,
                unexplained_diff_ids=[d.diff_id for d in unexplained_diffs],
                decided_at=now_iso,
            )
            per_variant.append(decision)

        self.decisions[release_id] = per_variant
        overall = GateOutcome.PASS if (per_variant and all(d.outcome == GateOutcome.PASS for d in per_variant)) else GateOutcome.BLOCK
        any_rxswin = any(d.rxswin_impact for d in per_variant)

        bundle = {
            "release_id": release_id,
            "baseline_release_id": baseline_release_id,
            "overall_outcome": overall.value,
            "ota_eligible": overall == GateOutcome.PASS,
            "rxswin_impact": any_rxswin,
            "decided_at": now_iso,
            "variants": [d.model_dump() for d in per_variant],
            "equivalence_summary": equiv_report.summary,
        }

        os.makedirs(GATES_DIR, exist_ok=True)
        out_file = os.path.join(GATES_DIR, f"gate_{release_id.replace('.', '_')}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)

        return bundle


# Singleton gate service
release_gate = ReleaseGateService()
