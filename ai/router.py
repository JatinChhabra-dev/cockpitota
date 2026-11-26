"""
Module 6 AI Layer REST API (Spec §6).
Endpoints:
  - POST /v1/releases/{release_id}/ai/test-proposals   (M6-FR1)
  - GET  /v1/test-proposals                             (list review queue)
  - POST /v1/test-proposals/{proposal_id}/review        (M6-FR2 approve/edit/reject)
  - POST /v1/ai/triage                                  (M6-FR3 failure triage from real M5 run)
  - POST /v1/ai/visual-diff                             (M6-FR4 visual-diff classification)
  - GET  /v1/ai/records                                 (M6-FR5 audit evidence log)
  - POST /v1/ai/toggle                                  (enable/disable AI layer)
  - GET  /v1/ai/status
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai.models import ReviewProposalRequest, TriageRequest, VisualClassifyRequest
from ai.store import ai_service

router = APIRouter(prefix="/v1", tags=["M6 AI Layer & Human Review Queue"])


class ToggleRequest(BaseModel):
    enabled: bool


@router.get("/ai/status")
def get_ai_status():
    return {
        "enabled": ai_service.enabled,
        "provider": ai_service.adapter.provider,
        "model": ai_service.adapter.model,
        "records_count": len(ai_service.records),
        "proposals_count": len(ai_service.proposals),
    }


@router.post("/ai/toggle")
def toggle_ai(req: ToggleRequest):
    ai_service.enabled = req.enabled
    return {"enabled": ai_service.enabled}


@router.post("/releases/{release_id}/ai/test-proposals")
def generate_test_proposals(release_id: str):
    try:
        return ai_service.generate_test_proposals(release_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/test-proposals")
def list_test_proposals(release_id: str | None = None, status: str | None = None):
    items = ai_service.list_proposals(release_id=release_id, status=status)
    return {"proposals": items, "total": len(items)}


@router.post("/test-proposals/{proposal_id}/review")
def review_test_proposal(proposal_id: str, req: ReviewProposalRequest):
    try:
        return ai_service.review_proposal(proposal_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/ai/triage")
def run_ai_triage(req: TriageRequest):
    try:
        return ai_service.triage_failure(req)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/ai/visual-diff")
def run_visual_diff_classification(req: VisualClassifyRequest):
    try:
        return ai_service.classify_visual_diff(req)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/ai/records")
def list_ai_records():
    recs = ai_service.list_records()
    return {"records": recs, "total": len(recs)}
