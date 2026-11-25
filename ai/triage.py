"""
Defect Triage Engine
Formats diagnostic bundles, invokes the LLM adapter, and stores auditable AIRecords.
"""

import os
from typing import Any, Dict, Optional
from ai.adapter import LLMAdapter

class DefectTriageEngine:
    def __init__(self, adapter: Optional[LLMAdapter] = None):
        self.adapter = adapter or LLMAdapter()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_file = os.path.join(base_dir, "prompts", "triage_v1.txt")
        with open(prompt_file, "r", encoding="utf-8") as f:
            self.template = f.read()

    def triage_failure(self, failure_bundle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes a failure bundle dictionary:
        {
          "scenario_id": "SC-03",
          "scenario_name": "Reverse with menu open",
          "variant_id": "VAR-B",
          "variant_layout": "Portrait 1080x1920",
          "locale": "en-US",
          "step_index": 3,
          "simulated_time": 4.0,
          "phase": "shift_reverse",
          "expected": "APP-2 Rear-view stand-in visible within 500ms of GEAR_REVERSE",
          "actual": "APP-2 not rendered; charging modal occupies top window after 2000ms",
          "ui_hierarchy": "<xml>...",
          "logcat": "...",
          "visual_diagnostic": "..."
        }
        """
        prompt = self.template
        prompt = prompt.replace("{{SCENARIO_ID}}", str(failure_bundle.get("scenario_id", "")))
        prompt = prompt.replace("{{SCENARIO_NAME}}", str(failure_bundle.get("scenario_name", "")))
        prompt = prompt.replace("{{VARIANT_ID}}", str(failure_bundle.get("variant_id", "")))
        prompt = prompt.replace("{{VARIANT_LAYOUT}}", str(failure_bundle.get("variant_layout", "")))
        prompt = prompt.replace("{{LOCALE}}", str(failure_bundle.get("locale", "en-US")))
        prompt = prompt.replace("{{STEP_INDEX}}", str(failure_bundle.get("step_index", "")))
        prompt = prompt.replace("{{SIMULATED_TIME}}", str(failure_bundle.get("simulated_time", "")))
        prompt = prompt.replace("{{PHASE}}", str(failure_bundle.get("phase", "")))
        prompt = prompt.replace("{{EXPECTED_BEHAVIOR}}", str(failure_bundle.get("expected", "")))
        prompt = prompt.replace("{{ACTUAL_BEHAVIOR}}", str(failure_bundle.get("actual", "")))
        prompt = prompt.replace("{{UI_HIERARCHY}}", str(failure_bundle.get("ui_hierarchy", "N/A")))
        prompt = prompt.replace("{{LOGCAT_SNIPPET}}", str(failure_bundle.get("logcat", "N/A")))
        prompt = prompt.replace("{{VISUAL_DIAGNOSTIC}}", str(failure_bundle.get("visual_diagnostic", "Visual difference detected")))

        system_prompt = "You are the Ferfier Release Assurance AI Copilot. Output only valid JSON."
        result = self.adapter.complete(prompt, system_prompt=system_prompt)

        # Build auditable AIRecord per Spec Section 5
        ai_record = {
            "task": "FAILURE_TRIAGE",
            "model": result["model"],
            "provider": result["provider"],
            "prompt_version": "triage_v1",
            "input_hash": result["input_hash"],
            "latency_ms": result["latency_ms"],
            "output": result["parsed"] or result["raw_output"],
            "reviewer": None,
            "decision": "PENDING_REVIEW"
        }
        return ai_record
