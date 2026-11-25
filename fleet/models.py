"""
Fleet Manager — Pydantic models
Shared across fleet/manager.py and the REST API layer (M7).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class InstanceStatus(str, enum.Enum):
    STARTING  = "STARTING"
    ONLINE    = "ONLINE"
    STOPPING  = "STOPPING"
    STOPPED   = "STOPPED"
    ERROR     = "ERROR"


class VariantConfig(BaseModel):
    id: str
    name: str
    avd_name: str
    display: Dict[str, object]
    locale: str
    feature_flags: Dict[str, str]
    system_props: Dict[str, str]
    description: str = ""


class FleetInstance(BaseModel):
    instance_id: str                   # e.g. "inst-vara-001"
    variant_id: str                    # "VAR-A" | "VAR-B" | "VAR-C"
    vin_like: str                      # e.g. "ZFA000000000VAR-A"
    build_tag: str                     # e.g. "v1.0" or "v1.1"
    adb_serial: Optional[str] = None  # "emulator-5554"
    adb_port: Optional[int] = None
    stream_url: Optional[str] = None
    status: InstanceStatus = InstanceStatus.STARTING
    pid: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    boot_time_seconds: Optional[float] = None
    properties: Dict[str, str] = {}


class LaunchRequest(BaseModel):
    variant_id: str                    # "VAR-A" | "VAR-B" | "VAR-C"
    build_tag: str = "v1.0"
    count: int = Field(default=1, ge=1, le=5)


class LaunchResponse(BaseModel):
    instances: List[FleetInstance]


class InstanceListResponse(BaseModel):
    instances: List[FleetInstance]
    total: int
