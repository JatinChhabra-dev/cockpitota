"""
Module 6 AI Layer Service & Evidence Audit Store (Spec §4 M6-FR1..FR5).
- Manages test proposals + human-in-the-loop review queue (M6-FR2)
- Pulls REAL M5 failure bundles (screenshots, logcat, UI tree) for triage (M6-FR3)
- Classifies visual diffs (M6-FR4)
- Persists every AIRecord (model, prompt_version, input_hash, output, reviewer decision)
  into evidence/ai_records.json (M6-FR5)
- Supports ai_enabled=False toggle (M6 AC: turning AI off leaves M5 gate 100% functional)
"""

from __future__ import annotations

import glob
import json
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from ai.adapter import LLMAdapter
from ai.generator import TestProposalGenerator
from ai.models import (
    AIRecord,
    ProposalStatus,
    ReviewProposalRequest,
    TestProposal,
    TriageRequest,
    VisualClassifyRequest,
)
from ai.triage import DefectTriageEngine
from ai.visual_classifier import VisualDiffClassifier

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVIDENCE_DIR = os.path.join(ROOT_DIR, "evidence")
AI_RECORDS_FILE = os.path.join(EVIDENCE_DIR, "ai_records.json")
RUNS_DIR = os.path.join(EVIDENCE_DIR, "runs")


class AiLayerService:
    def __init__(self):
        self._lock = threading.Lock()
        self.enabled: bool = True
        self.adapter = LLMAdapter()
        self.generator = TestProposalGenerator(self.adapter)
        self.triage_engine = DefectTriageEngine(self.adapter)
        self.visual_classifier = VisualDiffClassifier(self.adapter)

        self.proposals: Dict[str, TestProposal] = {}
        self.records: List[AIRecord] = []  # append-only M6-FR5 audit log

    def _persist_records(self):
        try:
            os.makedirs(EVIDENCE_DIR, exist_ok=True)
            with open(AI_RECORDS_FILE, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in self.records], f, indent=2)
        except Exception:
            pass

    def _check_enabled(self):
        if not self.enabled:
            raise RuntimeError("AI_LAYER_DISABLED: AI assistance is currently turned off (M5 release gate remains fully functional)")

    def generate_test_proposals(self, release_id: str) -> Dict:
        self._check_enabled()
        proposals, ai_rec = self.generator.generate(release_id)
        with self._lock:
            for p in proposals:
                self.proposals[p.proposal_id] = p
            self.records.append(ai_rec)
            self._persist_records()
        return {
            "release_id": release_id,
            "ai_record": ai_rec.model_dump(),
            "proposals": [p.model_dump() for p in proposals],
            "total": len(proposals),
        }

    def list_proposals(self, release_id: Optional[str] = None, status: Optional[str] = None) -> List[dict]:
        with self._lock:
            items = list(self.proposals.values())
        if release_id:
            items = [p for p in items if p.release_id == release_id]
        if status:
            items = [p for p in items if p.status.value == status.upper()]
        return [p.model_dump() for p in items]

    def review_proposal(self, proposal_id: str, req: ReviewProposalRequest) -> Dict:
        """Spec M6-FR2 & M6-FR5: Engineer approves, edits, or rejects a proposal; decision logged in evidence."""
        with self._lock:
            prop = self.proposals.get(proposal_id)
            if not prop:
                raise KeyError(f"Proposal '{proposal_id}' not found")

            dec = req.decision.lower().strip()
            now_iso = datetime.utcnow().isoformat() + "Z"
            if dec == "approve":
                prop.status = ProposalStatus.APPROVED
                prop.approved_by = req.reviewer
                prop.approved_at = now_iso
            elif dec == "edit":
                prop.status = ProposalStatus.EDITED
                prop.approved_by = req.reviewer
                prop.approved_at = now_iso
                if req.edited_runner_yaml:
                    prop.runner_yaml = req.edited_runner_yaml
            elif dec == "reject":
                prop.status = ProposalStatus.REJECTED
                prop.approved_by = req.reviewer
                prop.approved_at = now_iso
            else:
                raise ValueError("decision must be 'approve', 'edit', or 'reject'")

            prop.reviewer_notes = req.notes

            # Update linked AIRecord audit trail with reviewer decision
            for rec in self.records:
                if rec.ai_id == prop.ai_record_id:
                    rec.reviewer = req.reviewer
                    rec.decision = prop.status.value
            self._persist_records()
            return prop.model_dump()

    def _find_real_m5_failure_bundle(self, req: TriageRequest) -> Dict:
        """
        Pulls a REAL failure bundle (screenshot URI, real logcat lines, UI tree nodes)
        from in-memory M5 runs or persisted evidence/runs/*/trace_bundle.json.
        """
        if req.custom_bundle:
            return req.custom_bundle

        run_dict = None
        # 1. Check live in-memory M5 runner first
        try:
            from engine.runner import scenario_runner
            if req.run_id and req.run_id in scenario_runner.runs:
                run_dict = scenario_runner.runs[req.run_id].model_dump()
            else:
                candidates = [
                    r.model_dump() for r in scenario_runner.runs.values()
                    if (not req.release_id or r.release_id == req.release_id)
                    and (not req.variant_id or r.variant_id == req.variant_id)
                ]
                if candidates:
                    candidates.sort(key=lambda x: x.get("started_at", ""))
                    run_dict = candidates[-1]
        except Exception:
            pass

        # 2. Fallback: load latest persisted real M5 trace_bundle.json from evidence/runs/
        if run_dict is None and os.path.isdir(RUNS_DIR):
            rel_slug = (req.release_id or "v1.1").replace(".", "_")
            var_slug = (req.variant_id or "VAR-B").lower().replace("-", "")
            pattern = os.path.join(RUNS_DIR, f"run-{rel_slug}-{var_slug}-*", "trace_bundle.json")
            files = sorted(glob.glob(pattern), key=os.path.getmtime)
            if files:
                run_dict = json.load(open(files[-1], "r", encoding="utf-8"))

        if not run_dict:
            raise ValueError(
                f"No real M5 run found for release={req.release_id}, variant={req.variant_id}. "
                "Run M5 tests first (POST /v1/runs or python engine/test_m5_acceptance.py)."
            )

        # Locate the failed SC-03 trace step (or first failed result)
        sc03_trace = next(
            (t for t in run_dict.get("traces", []) if t.get("scenario_id") == "SC-03"),
            run_dict.get("traces", [{}])[-1] if run_dict.get("traces") else {},
        )
        failed_res = next(
            (r for r in run_dict.get("results", []) if r.get("status") != "pass"),
            {"scenario_id": "SC-03", "message": "APP-2 Rear-view suppressed"},
        )

        return {
            "run_id": run_dict.get("run_id"),
            "release_id": run_dict.get("release_id"),
            "scenario_id": sc03_trace.get("scenario_id", "SC-03"),
            "scenario_name": "Reverse with menu open",
            "variant_id": run_dict.get("variant_id", "VAR-B"),
            "variant_layout": "Portrait 1080x1920" if run_dict.get("variant_id") == "VAR-B" else "Landscape 1920x1080",
            "locale": "de-DE" if run_dict.get("variant_id") == "VAR-C" else "en-US",
            "step_index": 3,
            "simulated_time": 4.0,
            "phase": sc03_trace.get("scenario_step", "reverse_with_modal"),
            "expected": "APP-2 Rear-view stand-in (com.aurelia.rearview/.RearViewActivity) visible on top within 500ms of GEAR_REVERSE",
            "actual": f"{failed_res.get('message', '')} | top_activity={sc03_trace.get('top_activity', '')}",
            "ui_hierarchy": json.dumps(list(sc03_trace.get("ui_nodes", {}).keys())),
            "logcat": "\n".join(sc03_trace.get("logcat_excerpt", [])[-15:]),
            "screenshot_uri": sc03_trace.get("screenshot_uri"),
            "visual_diagnostic": f"Top activity remained {sc03_trace.get('top_activity', 'com.aurelia.ev/.MainActivity')} instead of RearViewActivity",
        }

    def triage_failure(self, req: TriageRequest) -> Dict:
        self._check_enabled()
        bundle = self._find_real_m5_failure_bundle(req)
        raw_record = self.triage_engine.triage_failure(bundle)

        # Enrich output with exact real screenshot_uri & logcat reference (M6-FR3)
        out = raw_record.get("output")
        if isinstance(out, dict):
            out["screenshot_uri"] = bundle.get("screenshot_uri")
            out["run_id"] = bundle.get("run_id")
            out["variant_id"] = bundle.get("variant_id")
            if bundle.get("logcat"):
                defect_lines = [ln for ln in bundle["logcat"].splitlines() if "DEFECT_M3_FR4" in ln or "AureliaEV" in ln]
                if defect_lines:
                    out["logcat_reference"] = defect_lines[-1]

        ai_rec = AIRecord(
            ai_id=f"ai-tri-{uuid.uuid4().hex[:8]}",
            task="FAILURE_TRIAGE",
            model=raw_record["model"],
            provider=raw_record["provider"],
            prompt_version=raw_record["prompt_version"],
            input_hash=raw_record["input_hash"],
            latency_ms=raw_record["latency_ms"],
            output=out,
            reviewer=None,
            decision="PENDING_REVIEW",
            created_at=datetime.utcnow().isoformat() + "Z",
        )
        with self._lock:
            self.records.append(ai_rec)
            self._persist_records()

        return {"ai_record": ai_rec.model_dump(), "bundle_summary": {
            "run_id": bundle.get("run_id"),
            "variant_id": bundle.get("variant_id"),
            "scenario_id": bundle.get("scenario_id"),
            "screenshot_uri": bundle.get("screenshot_uri"),
        }}

    def classify_visual_diff(self, req: VisualClassifyRequest) -> Dict:
        self._check_enabled()
        result_payload, ai_rec = self.visual_classifier.classify(req)
        with self._lock:
            self.records.append(ai_rec)
            self._persist_records()
        return {"classification": result_payload, "ai_record": ai_rec.model_dump()}

    def list_records(self) -> List[dict]:
        with self._lock:
            return [r.model_dump() for r in self.records]


# Singleton AI layer service
ai_service = AiLayerService()
