"""
Module 5 Data Models — Test Runner, Trace Recorder, Equivalence Differ & Release Gate.
Aligned with Spec §4 (M5), §5 (Data Model), and §8 (Equivalence Rules).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TestStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    FLAKY = "flaky"
    SKIPPED = "skipped"


class DiffClass(str, Enum):
    DECLARED = "declared"
    COSMETIC = "cosmetic"
    UNEXPLAINED = "unexplained"


class GateOutcome(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


class UiNode(BaseModel):
    resource_id: str
    text: str = ""
    enabled: bool = True
    focused: bool = False
    bounds: str = ""


class TraceStep(BaseModel):
    """Spec §5 Data Model — Basis for equivalence diffing."""
    run_id: str
    scenario_id: str
    scenario_step: str
    variant_id: str
    top_activity: str = ""
    ui_hash: str = ""
    ui_nodes: Dict[str, UiNode] = Field(default_factory=dict)  # resource_id -> UiNode
    property_reads: Dict[str, Any] = Field(default_factory=dict)
    timing_ms: Optional[float] = None
    screenshot_uri: Optional[str] = None
    logcat_excerpt: List[str] = Field(default_factory=list)
    safety_relevant: bool = False
    timestamp: str


class TestResult(BaseModel):
    """Spec §5 Data Model — Result of one suite check on one variant."""
    result_id: str
    run_id: str
    test_id: str
    suite: str  # functional | ux_restriction | safety_display | visual | localisation
    scenario_id: str
    status: TestStatus
    message: str = ""
    timing_ms: Optional[float] = None
    retries: int = 0
    evidence_uris: List[str] = Field(default_factory=list)


class RunRecord(BaseModel):
    """Spec §5 Data Model — One complete test execution on one (release, variant) pair."""
    run_id: str
    release_id: str
    variant_id: str
    instance_id: str
    adb_serial: str
    scenarios: List[str] = Field(default_factory=list)
    status: str = "COMPLETED"  # RUNNING | COMPLETED | ERROR
    started_at: str
    ended_at: Optional[str] = None
    wall_time_seconds: float = 0.0
    compute_minutes: float = 0.0
    cost_usd: float = 0.0
    results: List[TestResult] = Field(default_factory=list)
    traces: List[TraceStep] = Field(default_factory=list)
    junit_xml_path: Optional[str] = None
    trace_json_path: Optional[str] = None


class Difference(BaseModel):
    """Spec §5 Data Model — Output of M5 Equivalence Differ."""
    diff_id: str
    baseline_run: str
    candidate_run: str
    variant_id: str
    step: str
    kind: str  # ui_added | ui_removed | ui_text | ui_enabled | z_order | property | timing | visual
    diff_class: DiffClass
    change_id: Optional[str] = None
    ui_id: Optional[str] = None
    baseline_value: Any = None
    candidate_value: Any = None
    detail: str = ""
    evidence_uris: List[str] = Field(default_factory=list)


class EquivalenceReport(BaseModel):
    release_id: str
    baseline_release_id: str
    generated_at: str
    variants_compared: List[str] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)  # declared, cosmetic, unexplained, total
    differences: List[Difference] = Field(default_factory=list)


class GateDecision(BaseModel):
    """Spec §5 Data Model — One per variant per release."""
    gate_id: str
    release_id: str
    baseline_release_id: str
    variant_id: str
    outcome: GateOutcome
    reasons: List[str] = Field(default_factory=list)
    rxswin_impact: bool = False
    rxswin_components: List[str] = Field(default_factory=list)
    failed_tests: List[str] = Field(default_factory=list)
    unexplained_diff_ids: List[str] = Field(default_factory=list)
    decided_at: str


class StartRunRequest(BaseModel):
    release_id: str = Field(..., description="e.g. 'v1.0', 'v1.1', 'v1.1-fix'")
    variants: Optional[List[str]] = Field(default=None, description="Defaults to all currently ONLINE variants")
    scenarios: List[str] = Field(default_factory=lambda: ["SC-01", "SC-02", "SC-03", "SC-04"])
