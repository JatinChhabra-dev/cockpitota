"""
Module 4 OTA Data Models — aligned with Spec §4 (M4), §5 (Data Model), §6 (APIs).
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class AgentState(str, Enum):
    IDLE = "IDLE"
    POLLING = "POLLING"
    DOWNLOADING = "DOWNLOADING"
    VERIFYING = "VERIFYING"
    WAIT_PRECOND = "WAIT_PRECOND"
    INSTALLING = "INSTALLING"
    REPORTING = "REPORTING"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


class CampaignStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CANCELED = "CANCELED"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


class UpdateOutcome(str, Enum):
    PENDING = "PENDING"
    DEFERRED = "DEFERRED"
    INSTALLED = "INSTALLED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


class RolloutGroup(BaseModel):
    group_index: int
    name: str
    percentage: int
    target_vehicle_ids: List[str]
    status: str = "WAITING"  # WAITING | RUNNING | FINISHED | PAUSED | CANCELED
    success_threshold_pct: int = 100
    installed_count: int = 0
    deferred_count: int = 0
    failed_count: int = 0


class PreconditionSnapshot(BaseModel):
    gear: int = 4                 # 4 = GEAR_PARK
    speed_ms: float = 0.0
    parking_brake: bool = True
    soc_percent: float = 80.0
    passed: bool = True
    defer_reasons: List[str] = Field(default_factory=list)


class UpdateRecord(BaseModel):
    """Spec §5 Data Model — R156 per-vehicle update ledger record."""
    record_id: str
    vehicle_id: str
    vin_like: str
    variant_id: str
    campaign_id: str
    release_id: str
    group_index: int
    pre_versions: Dict[str, str] = Field(default_factory=dict)
    post_versions: Dict[str, str] = Field(default_factory=dict)
    agent_state: AgentState = AgentState.IDLE
    outcome: UpdateOutcome = UpdateOutcome.PENDING
    defer_reasons: List[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    artefact_sha256: Optional[str] = None
    signature_verified: bool = False
    started_at: str
    ended_at: Optional[str] = None


class Campaign(BaseModel):
    """Spec §5 Data Model — OTA Campaign mirroring Eclipse hawkBit."""
    campaign_id: str
    release_id: str
    apk_filename: str
    package_name: str = "com.aurelia.ev"
    target_version: str
    artefact_sha256: str
    signature_hex: str
    hawkbit_rollout_id: Optional[str] = None
    hawkbit_mode: str = "LOCAL_MIRROR"  # HAWKBIT_LIVE | LOCAL_MIRROR
    status: CampaignStatus = CampaignStatus.CREATED
    groups: List[RolloutGroup] = Field(default_factory=list)
    created_at: str
    updated_at: str


class CreateCampaignRequest(BaseModel):
    release_id: str = Field(..., description="e.g. 'v1.1-fix'")
    apk_filename: str = Field(default="aurelia-ev-v1.1-fix.apk")
    package_name: str = Field(default="com.aurelia.ev")
    target_version: str = Field(default="1.1.1-fix")
    gate_passed: bool = Field(default=True, description="M4 gate adapter blocks rollout unless gate passed")
    vehicle_ids: Optional[List[str]] = Field(default=None, description="Optional explicit target fleet")
    target_mode: str = Field(default="virtual10", description="'live' = only real ONLINE AAOS cockpits; 'virtual10' = 10-vehicle M1-FR7 fleet")
    auto_start: bool = Field(default=True)
    tamper_test: bool = Field(default=False, description="If true, deliberately corrupts signature/hash for M4-FR3 test")


class VehicleSimStateRequest(BaseModel):
    gear: Optional[str] = Field(default=None, description="GEAR_PARK | GEAR_DRIVE | GEAR_REVERSE | GEAR_NEUTRAL")
    speed_kmh: Optional[float] = Field(default=None, ge=0.0, le=250.0)
    parking_brake: Optional[bool] = Field(default=None)
    soc_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)
