"""
Module 6 AI Layer Data Models (Spec §4 M6, §5 Data Model: TestCase, AIRecord).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProposalStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"


class VisualClass(str, Enum):
    DEFECT = "DEFECT"
    COSMETIC = "COSMETIC"
    DECLARED = "DECLARED"


class TestProposal(BaseModel):
    """Spec §5 TestCase (origin = ai) awaiting human approval in review queue."""
    proposal_id: str
    release_id: str
    origin: str = "ai"
    title: str
    suite: str  # functional | ux_restriction | safety_display | visual | localisation
    scenario_ref: str
    target_variants: List[str] = Field(default_factory=list)
    linked_change_id: Optional[str] = None
    rationale: str
    runner_yaml: str
    status: ProposalStatus = ProposalStatus.PENDING_REVIEW
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    reviewer_notes: Optional[str] = None
    ai_record_id: str


class ReviewProposalRequest(BaseModel):
    decision: str = Field(..., description="approve | edit | reject")
    reviewer: str = Field(default="QA Lead")
    notes: Optional[str] = None
    edited_runner_yaml: Optional[str] = None


class TriageRequest(BaseModel):
    run_id: Optional[str] = Field(default=None, description="M5 RunRecord ID to triage automatically from real evidence")
    release_id: Optional[str] = Field(default="v1.1", description="Fallback: locate latest failed M5 run for this release")
    variant_id: Optional[str] = Field(default="VAR-B")
    custom_bundle: Optional[Dict[str, Any]] = None


class VisualClassifyRequest(BaseModel):
    baseline_screenshot: Optional[str] = None
    candidate_screenshot: Optional[str] = None
    diff_mask: Optional[str] = None
    diff_pct: float = 0.0
    variant_id: str = "VAR-B"
    step: str = "SC-03:reverse_with_modal"
    ui_id: Optional[str] = None
    change_id: Optional[str] = None
    safety_relevant: bool = False
    description: str = ""


class AIRecord(BaseModel):
    """Spec §5 Data Model — Immutable evidence record for every AI invocation."""
    ai_id: str
    task: str  # TEST_GENERATION | FAILURE_TRIAGE | VISUAL_DIFF_CLASSIFICATION
    model: str
    provider: str
    prompt_version: str
    input_hash: str
    latency_ms: float
    output: Any
    reviewer: Optional[str] = None
    decision: str = "PENDING_REVIEW"
    created_at: str
