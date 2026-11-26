"""
APP-3: Companion Phone App & Mock Vehicle Cloud Router (Spec §4 M3, §7 SC-04)
Receives remote climate & charging-schedule commands from the Companion App
and dispatches them to the target virtual AAOS cockpit via VHAL.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("apps.companion.cloud")

router = APIRouter(prefix="/v1/cloud", tags=["APP-3 Mock Vehicle Cloud"])

# In-memory command ledger per instance/vehicle
_command_ledger: Dict[str, List[dict]] = {}
_charge_schedules: Dict[str, dict] = {}


class RemoteClimateRequest(BaseModel):
    temperature_c: float = Field(..., ge=15.0, le=30.0, description="Target cabin temperature in Celsius")
    source: str = Field(default="APP-3-Companion", description="Originating companion client")


class RemoteChargeScheduleRequest(BaseModel):
    target_soc: int = Field(default=80, ge=20, le=100)
    start_time: str = Field(default="23:00")
    end_time: str = Field(default="06:00")
    precondition: bool = Field(default=True)


@router.post("/vehicles/{instance_id}/climate")
def send_remote_climate(instance_id: str, req: RemoteClimateRequest):
    """
    SC-04 flow: Companion app -> Mock Vehicle Cloud -> Cockpit VHAL (HVAC_TEMPERATURE_SET).
    """
    from fleet.manager import _instances, _lock, _get_injector
    from fleet.models import InstanceStatus

    with _lock:
        inst = _instances.get(instance_id)

    if not inst:
        raise HTTPException(status_code=404, detail=f"Vehicle instance '{instance_id}' not found")
    if inst.status != InstanceStatus.ONLINE or not inst.adb_serial:
        raise HTTPException(status_code=409, detail=f"Vehicle instance '{instance_id}' is not ONLINE")

    injector = _get_injector(inst.adb_serial)
    vhal_res = injector.set_hvac_temperature(req.temperature_c, row=49)
    try:
        injector._exec_adb([
            "shell", "am", "broadcast",
            "-a", "com.aurelia.ev.ACTION_REMOTE_CLIMATE",
            "--ef", "temperature_c", str(req.temperature_c),
            "-n", "com.aurelia.ev/.RemoteCommandReceiver",
        ])
    except Exception:
        pass

    record = {
        "command_id": f"cmd-{int(datetime.utcnow().timestamp() * 1000)}",
        "vehicle_id": instance_id,
        "vin": inst.vin_like,
        "variant_id": inst.variant_id,
        "type": "REMOTE_CLIMATE",
        "payload": {"temperature_c": req.temperature_c},
        "source": req.source,
        "status": "DELIVERED",
        "latency_ms": vhal_res.get("latency_ms", 0),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    _command_ledger.setdefault(instance_id, []).insert(0, record)
    logger.info("[CLOUD -> %s] Remote climate %.1f C delivered (%.1f ms)", instance_id, req.temperature_c, record["latency_ms"])
    return {"command": record, "vhal": vhal_res}


@router.post("/vehicles/{instance_id}/charge-schedule")
def send_remote_charge_schedule(instance_id: str, req: RemoteChargeScheduleRequest):
    """Stores and acknowledges a remote off-peak charging schedule from APP-3 Companion."""
    schedule = req.model_dump()
    schedule["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _charge_schedules[instance_id] = schedule

    record = {
        "command_id": f"cmd-{int(datetime.utcnow().timestamp() * 1000)}",
        "vehicle_id": instance_id,
        "type": "REMOTE_CHARGE_SCHEDULE",
        "payload": schedule,
        "source": "APP-3-Companion",
        "status": "DELIVERED",
        "timestamp": schedule["updated_at"],
    }
    _command_ledger.setdefault(instance_id, []).insert(0, record)
    return {"command": record, "schedule": schedule}


@router.get("/vehicles/{instance_id}/commands")
def get_vehicle_commands(instance_id: str):
    """Returns remote companion command history and active charging schedule."""
    return {
        "vehicle_id": instance_id,
        "schedule": _charge_schedules.get(instance_id),
        "commands": _command_ledger.get(instance_id, []),
    }
