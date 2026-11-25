"""
Scenario Replay Controller
Executes VSS time-series scenarios with deterministic timing and records traces for equivalence verification.
"""

import json
import os
import time
from typing import Callable, Dict, List, Optional
import yaml
from signals.injector import VhalInjector

class ScenarioReplayController:
    def __init__(self, injector: VhalInjector, speed_factor: float = 1.0, instance_id: str = "inst-001"):
        self.injector = injector
        self.speed_factor = max(0.1, speed_factor)
        self.instance_id = instance_id
        self.trace_log: List[Dict] = []
        self._action_handlers: Dict[str, Callable] = {}

    def register_action_handler(self, action_name: str, handler: Callable):
        """Registers a callback for non-VHAL actions (e.g., UI Automator taps, mock cloud events)."""
        self._action_handlers[action_name] = handler

    def load_scenario(self, scenario_path: str) -> Dict:
        if not os.path.isabs(scenario_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            scenario_path = os.path.join(base_dir, "scenarios", scenario_path)
            if not scenario_path.endswith(".yaml"):
                scenario_path += ".yaml"

        with open(scenario_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def replay(self, scenario_path_or_dict, on_step_callback: Optional[Callable] = None) -> List[Dict]:
        """
        Executes scenario steps deterministically.
        Records an append-only trace log matching M2-FR4 and M7 TraceStep schema.
        """
        if isinstance(scenario_path_or_dict, dict):
            scenario = scenario_path_or_dict
        else:
            scenario = self.load_scenario(scenario_path_or_dict)

        scenario_id = scenario.get("scenario_id", "UNKNOWN")
        steps = scenario.get("steps", [])
        
        print(f"\n--- Starting Replay: {scenario_id} ({scenario.get('name')}) at {self.speed_factor}x speed ---")
        self.trace_log = []
        start_mono = time.monotonic()

        for idx, step in enumerate(steps):
            step_t = float(step.get("t", 0.0))
            phase = step.get("phase", "default")
            
            # Anchor to monotonic start time to prevent cumulative drift (M2-FR4: ±100 ms determinism)
            target_mono = start_mono + (step_t / self.speed_factor)
            sleep_for = target_mono - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            actual_elapsed_s = round(time.monotonic() - start_mono, 3)

            trace_entry = {
                "instance_id": self.instance_id,
                "scenario_id": scenario_id,
                "step_index": idx,
                "simulated_time_s": step_t,
                "actual_elapsed_s": actual_elapsed_s,
                "drift_ms": round((actual_elapsed_s - (step_t / self.speed_factor)) * 1000, 1),
                "timestamp": time.time(),
                "phase": phase,
                "description": step.get("description", "")
            }

            # Handle signal injection
            if "signal" in step:
                sig_name = step["signal"]
                sig_val = step["value"]
                res = self.injector.inject_vss(sig_name, sig_val)
                trace_entry.update({
                    "kind": "SIGNAL_INJECTION",
                    "signal": sig_name,
                    "injected_value": res["injected_value"],
                    "latency_ms": res["latency_ms"],
                    "vhal_property_id": res["vhal_property_id"]
                })
                print(f"[{step_t:5.1f}s] Injected {sig_name} -> {res['injected_value']} (Latency: {res['latency_ms']}ms)")

            # Handle action triggers (UI / external commands)
            elif "action" in step:
                action_name = step["action"]
                action_val = step.get("value")
                trace_entry.update({
                    "kind": "ACTION_TRIGGER",
                    "action": action_name,
                    "action_value": action_val
                })
                print(f"[{step_t:5.1f}s] Action: {action_name}")
                if action_name in self._action_handlers:
                    self._action_handlers[action_name](action_val)

            self.trace_log.append(trace_entry)
            if on_step_callback:
                on_step_callback(trace_entry)

        total_wall_time = round(time.monotonic() - start_mono, 2)
        print(f"--- Completed {scenario_id} in {total_wall_time}s wall time. Generated {len(self.trace_log)} trace points. ---\n")

        # Persist append-only trace artifact for M5/M7 evidence store
        try:
            traces_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evidence", "traces")
            os.makedirs(traces_dir, exist_ok=True)
            trace_file = os.path.join(traces_dir, f"{scenario_id}_{self.instance_id}_{int(time.time())}.json")
            with open(trace_file, "w", encoding="utf-8") as tf:
                json.dump({
                    "scenario_id": scenario_id,
                    "scenario_version": scenario.get("version", "1.0"),
                    "instance_id": self.instance_id,
                    "speed_factor": self.speed_factor,
                    "wall_time_seconds": total_wall_time,
                    "steps": self.trace_log,
                }, tf, indent=2)
        except Exception:
            pass

        return self.trace_log
