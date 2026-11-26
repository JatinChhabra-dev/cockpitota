"""
AI Adapter Layer for Cockpit & OTA Release Assurance (Spec §3, §6.1).
Provider-agnostic interface supporting Google Gemini (default via .env), Anthropic Claude,
or offline deterministic rule engine when no API key is configured.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger("ai.adapter")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT_DIR, ".env")


def _load_dotenv(env_path: str = ENV_FILE):
    """Lightweight .env loader (no external dependency required; does not overwrite existing env vars)."""
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and val and not os.environ.get(key):
                    os.environ[key] = val
    except Exception as exc:
        logger.warning("Could not parse .env file: %s", exc)


class LLMAdapter:
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        _load_dotenv()
        self.provider = (provider or os.environ.get("AI_PROVIDER", "auto")).lower().strip()
        self.model = model
        self.api_key: Optional[str] = None
        self.client: Any = None
        self._init_client()

    def _init_client(self):
        gemini_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
        anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

        # 1. Google Gemini (preferred when AI_PROVIDER=gemini or GEMINI_API_KEY is set)
        if gemini_key and self.provider in ("gemini", "auto"):
            self.provider = "gemini"
            self.api_key = gemini_key
            self.model = self.model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
            logger.info("AI Adapter configured for live Google Gemini (%s)", self.model)
            return

        # 2. Anthropic Claude
        if anthropic_key and self.provider in ("anthropic", "auto"):
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=anthropic_key)
                self.provider = "anthropic"
                self.api_key = anthropic_key
                self.model = self.model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
                logger.info("AI Adapter configured for live Anthropic Claude (%s)", self.model)
                return
            except ImportError:
                pass

        # 3. Fallback to deterministic offline rule engine
        self.provider = "local_rule_engine"
        self.model = "cora-rule-engine-v1"
        logger.info("AI Adapter using offline rule engine (set GEMINI_API_KEY in .env to enable live Gemini)")

    def _call_gemini_rest(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Calls Google Gemini generateContent REST API directly (zero extra SDK dependency)."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {data}")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip()

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Executes LLM completion and produces an auditable AIRecord."""
        input_payload = f"{system_prompt or ''}\n---\n{prompt}"
        input_hash = hashlib.sha256(input_payload.encode("utf-8")).hexdigest()
        start_t = time.perf_counter()

        used_provider = self.provider
        used_model = self.model
        raw_text = ""

        if self.provider == "gemini" and self.api_key:
            try:
                raw_text = self._call_gemini_rest(prompt, system_prompt=system_prompt)
            except Exception as exc:
                logger.warning("Live Gemini call failed (%s); falling back to local rule engine", exc)
                used_provider = "local_rule_engine_fallback"
                used_model = "cora-rule-engine-v1"
                raw_text = self._mock_triage_eval(prompt)
        elif self.provider == "anthropic" and self.client is not None:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = resp.content[0].text
        else:
            raw_text = self._mock_triage_eval(prompt)

        latency_ms = round((time.perf_counter() - start_t) * 1000, 2)

        # Parse JSON if possible
        parsed_json = None
        clean_text = raw_text.strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].split("```")[0].strip()

        try:
            parsed_json = json.loads(clean_text)
        except Exception:
            pass

        return {
            "provider": used_provider,
            "model": used_model,
            "input_hash": input_hash,
            "latency_ms": latency_ms,
            "raw_output": raw_text,
            "parsed": parsed_json,
            "timestamp": time.time(),
        }

    def _mock_triage_eval(self, prompt: str) -> str:
        """Deterministic offline rule-engine for zero-cost rehearsals when no API key is configured."""
        if "SC-03" in prompt and ("VAR-B" in prompt or "portrait" in prompt.lower()):
            return json.dumps({
                "likely_cause": "APP-1 ChargingScheduleDialog retained modal focus on VAR-B portrait layout, suppressing RearViewActivity (APP-2) z-order elevation during GEAR_REVERSE",
                "affected_component": "com.aurelia.ev (APP-1)",
                "defect_category": "SAFETY_RELEVANT_BLOCK",
                "confidence": 0.98,
                "evidence_pointers": [
                    "AureliaEV: [DEFECT_M3_FR4] Portrait charging modal retained focus; suppressed APP-2 RearView overlay",
                    "Top Activity remained com.aurelia.ev/.MainActivity instead of com.aurelia.rearview/.RearViewActivity"
                ],
                "suggested_owner": "Cockpit HMI Team",
                "recommended_fix": "Dismiss chargingDialog cleanly on CarPropertyManager.GEAR_SELECTION == GEAR_REVERSE before launching RearViewActivity."
            }, indent=2)
        return json.dumps({
            "likely_cause": "Functional assertion failure during scenario execution",
            "affected_component": "SystemUnderInspection",
            "defect_category": "FUNCTIONAL_REGRESSION",
            "confidence": 0.85,
            "evidence_pointers": ["Check trace bundle and logcat window"],
            "suggested_owner": "QA Automation",
            "recommended_fix": "Review property trace and component logs."
        }, indent=2)
