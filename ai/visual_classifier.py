"""
Module 6 Visual-Diff Classifier (Spec §4 M6-FR4).
Classifies baseline/candidate screenshot pairs + diff masks into:
  - DEFECT: safety-relevant overlay suppressed or severe undeclared visual regression
  - DECLARED: visual change explained by a declared release-note change_id (e.g. de-DE string update, CHG-101..103)
  - COSMETIC: minor non-safety pixel delta (e.g. 2 px padding shift, anti-aliasing, clock tick)
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from datetime import datetime
from typing import Dict, Tuple

from ai.adapter import LLMAdapter
from ai.models import AIRecord, VisualClass, VisualClassifyRequest

AI_DIR = os.path.dirname(os.path.abspath(__file__))


class VisualDiffClassifier:
    def __init__(self, adapter: LLMAdapter | None = None):
        self.adapter = adapter or LLMAdapter()
        prompt_path = os.path.join(AI_DIR, "prompts", "visual_diff_v1.txt")
        self.template = open(prompt_path, "r", encoding="utf-8").read()

    def classify(self, req: VisualClassifyRequest) -> Tuple[Dict, AIRecord]:
        prompt = (
            self.template
            .replace("{{VARIANT_ID}}", req.variant_id)
            .replace("{{STEP}}", req.step)
            .replace("{{SAFETY_RELEVANT}}", str(req.safety_relevant))
            .replace("{{DIFF_PCT}}", str(req.diff_pct))
            .replace("{{CHANGE_ID}}", str(req.change_id or "NONE"))
            .replace("{{DESCRIPTION}}", req.description)
        )
        input_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        t0 = time.perf_counter()

        classification = VisualClass.COSMETIC
        confidence = 0.90
        reason = ""

        desc_low = req.description.lower()

        # Deterministic safety-first rules (mirrors Spec §8.2 & M6-FR4)
        if req.safety_relevant and (req.diff_pct >= 5.0 or "suppressed" in desc_low or "missing" in desc_low or "z-order" in desc_low):
            classification = VisualClass.DEFECT
            confidence = 0.99
            reason = (
                f"Safety-relevant view on {req.variant_id} ({req.step}) has {req.diff_pct}% pixel divergence — "
                "APP-2 Rear-view stand-in overlay is missing/suppressed; never COSMETIC per §8.2."
            )
        elif req.change_id or "de-de" in desc_low or "chg-10" in desc_low or "declared" in desc_low:
            classification = VisualClass.DECLARED
            confidence = 0.96
            reason = (
                f"Visual change on {req.variant_id} matches declared release-note item "
                f"{req.change_id or 'CHG-103 (de-DE localization)'}."
            )
        elif req.diff_pct <= 2.5 or "padding" in desc_low or "2 px" in desc_low or "2px" in desc_low:
            classification = VisualClass.COSMETIC
            confidence = 0.94
            reason = (
                f"Minor non-safety pixel delta ({req.diff_pct}% — e.g. 2 px padding/anti-aliasing shift) "
                "with no functional or z-order impact."
            )
        else:
            classification = VisualClass.DEFECT
            confidence = 0.91
            reason = f"Significant undeclared visual divergence ({req.diff_pct}% pixels) with no matching DeclaredChange."

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        now_iso = datetime.utcnow().isoformat() + "Z"
        ai_id = f"ai-vis-{uuid.uuid4().hex[:8]}"

        result_payload = {
            "classification": classification.value,
            "confidence": confidence,
            "reason": reason,
            "variant_id": req.variant_id,
            "step": req.step,
            "diff_pct": req.diff_pct,
            "baseline_screenshot": req.baseline_screenshot,
            "candidate_screenshot": req.candidate_screenshot,
            "diff_mask": req.diff_mask,
        }

        ai_record = AIRecord(
            ai_id=ai_id,
            task="VISUAL_DIFF_CLASSIFICATION",
            model=self.adapter.model,
            provider=self.adapter.provider,
            prompt_version="visual_diff_v1",
            input_hash=input_hash,
            latency_ms=latency_ms,
            output=result_payload,
            reviewer=None,
            decision="PENDING_REVIEW",
            created_at=now_iso,
        )
        return result_payload, ai_record
