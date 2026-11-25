"""
Scenario & Signal Simulator FastAPI Router (Spec §6)
Exposes endpoints for listing scenarios, triggering deterministic replay, and CAN import.
"""

import os
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
import yaml

from signals.injector import VhalInjector
from signals.replay import ScenarioReplayController
from signals.can_importer import import_can_csv_to_scenario

router = APIRouter(prefix="/v1/scenarios", tags=["scenarios"])

_SCENARIOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios")
_TRACES_STORE: Dict[str, List[Dict]] = {} # scenario_id -> list of trace runs

class ReplayRequest(BaseModel):
    instance_id: str
    speed_factor: float = Field(default=1.0, ge=0.1, le=10.0)
    adb_serial: Optional[str] = None

class ReplayResponse(BaseModel):
    scenario_id: str
    instance_id: str
    status: str
    step_count: int
    wall_time_seconds: float
    trace: List[Dict]

def _list_scenario_files() -> List[str]:
    if not os.path.isdir(_SCENARIOS_DIR):
        return []
    return [f for f in os.listdir(_SCENARIOS_DIR) if f.endswith(".yaml") or f.endswith(".yml")]

def _load_scenario(scenario_id: str) -> Dict:
    # Normalise: "SC-01" -> "sc01", "sc_01" -> "sc01", case-insensitive
    clean_id = scenario_id.lower().replace("-", "").replace("_", "")
    files = _list_scenario_files()
    for f in files:
        f_clean = f.lower().replace("-", "").replace("_", "")
        if f_clean.startswith(clean_id) or clean_id in f_clean:
            path = os.path.join(_SCENARIOS_DIR, f)
            with open(path, "r", encoding="utf-8") as yf:
                return yaml.safe_load(yf)
    raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found in catalogue")

@router.get("", response_model=List[Dict])
def list_scenarios():
    """List all scenarios available in the catalogue."""
    results = []
    for f in _list_scenario_files():
        path = os.path.join(_SCENARIOS_DIR, f)
        with open(path, "r", encoding="utf-8") as yf:
            data = yaml.safe_load(yf)
            results.append({
                "scenario_id": data.get("scenario_id", f),
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "version": data.get("version", "1.0"),
                "duration_seconds": data.get("duration_seconds", 0),
                "step_count": len(data.get("steps", []))
            })
    return results

@router.get("/{scenario_id}")
def get_scenario(scenario_id: str):
    """Retrieve full scenario specification and steps."""
    return _load_scenario(scenario_id)

@router.post("/{scenario_id}/replay", response_model=ReplayResponse)
def replay_scenario(scenario_id: str, request: ReplayRequest):
    """
    Replay a scenario deterministically on a cockpit instance.
    Implements spec §6: POST /v1/scenarios/{id}/replay
    """
    scenario_data = _load_scenario(scenario_id)
    
    # Resolve ADB serial
    serial = request.adb_serial
    if not serial:
        # 1) Check active instance registry if available
        try:
            from fleet.manager import _instances
            if request.instance_id in _instances:
                serial = _instances[request.instance_id].adb_serial
            elif _instances:
                # Fall back to first online instance
                for inst in _instances.values():
                    if inst.adb_serial:
                        serial = inst.adb_serial
                        break
        except Exception:
            pass
    if not serial:
        # 2) Fall back to first connected ADB device
        try:
            import subprocess
            from fleet.avd_backend import _adb_path
            out = subprocess.check_output([_adb_path(), "devices"], text=True, timeout=5)
            for line in out.splitlines()[1:]:
                parts = line.strip().split()
                if len(parts) == 2 and parts[1] == "device":
                    serial = parts[0]
                    break
        except Exception:
            pass

    from fleet.avd_backend import _adb_path
    injector = VhalInjector(adb_path=_adb_path(), serial=serial)
    controller = ScenarioReplayController(
        injector=injector,
        speed_factor=request.speed_factor,
        instance_id=request.instance_id
    )

    try:
        trace_log = controller.replay(scenario_data)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Replay failed: {str(exc)}")

    # Store trace for M5 / M7 equivalence & dossier
    if scenario_id not in _TRACES_STORE:
        _TRACES_STORE[scenario_id] = []
    _TRACES_STORE[scenario_id].append({
        "instance_id": request.instance_id,
        "speed_factor": request.speed_factor,
        "trace": trace_log
    })

    wall_secs = round(sum((float(t.get("latency_ms") or 0.0)) for t in trace_log) / 1000.0, 2)

    return ReplayResponse(
        scenario_id=scenario_id,
        instance_id=request.instance_id,
        status="COMPLETED",
        step_count=len(trace_log),
        wall_time_seconds=wall_secs,
        trace=trace_log
    )

@router.get("/{scenario_id}/traces")
def get_scenario_traces(scenario_id: str):
    """Retrieve historical replay traces for a scenario."""
    if scenario_id not in _TRACES_STORE:
        return {"scenario_id": scenario_id, "traces": []}
    return {"scenario_id": scenario_id, "traces": _TRACES_STORE[scenario_id]}
