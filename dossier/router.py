"""
Module 7 Releases, Measured Metrics & UNECE R156 Dossier REST API (Spec §6, §9).
Endpoints:
  - GET  /v1/releases
  - POST /v1/releases
  - GET  /v1/releases/{release_id}
  - GET  /v1/releases/{release_id}/dossier?format=json|html|pdf&reviewer=...
  - GET  /v1/metrics
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from dossier.generator import (
    _load_gate_for_release,
    _load_runs_for_release,
    assemble_dossier_json,
    collect_measured_metrics,
    render_dossier_html,
    render_dossier_pdf,
)

router = APIRouter(prefix="/v1", tags=["M7 Evidence Store & R156 Dossier"])

# Default registered POC releases (augmented by POST /v1/releases)
_releases: Dict[str, dict] = {
    "v1.0": {
        "release_id": "v1.0",
        "description": "Baseline Aurelia EV & Rear-view release (passes all variants)",
        "app_versions": ["com.aurelia.ev:1.0.0", "com.aurelia.rearview:1.0.0"],
        "created_by": "Release Engineering",
        "created_at": "2026-11-23T08:00:00Z",
    },
    "v1.1": {
        "release_id": "v1.1",
        "description": "Candidate release with CHG-101..103 + planted VAR-B portrait defect (M3-FR4)",
        "app_versions": ["com.aurelia.ev:1.1.0", "com.aurelia.rearview:1.0.0"],
        "created_by": "Release Engineering",
        "created_at": "2026-11-23T09:00:00Z",
    },
    "v1.1-fix": {
        "release_id": "v1.1-fix",
        "description": "Fix release retaining CHG-101..103 and removing only VAR-B portrait defect (M3-FR5)",
        "app_versions": ["com.aurelia.ev:1.1.1-fix", "com.aurelia.rearview:1.0.0"],
        "created_by": "Cockpit HMI Team",
        "created_at": "2026-11-23T10:00:00Z",
    },
}


class RegisterReleaseRequest(BaseModel):
    release_id: str
    description: str = ""
    app_versions: List[str] = Field(default_factory=list)
    created_by: str = "Release Engineering"


def _enrich_release(rel: dict) -> dict:
    rid = rel["release_id"]
    gate = _load_gate_for_release(rid)
    runs = _load_runs_for_release(rid)
    return {
        **rel,
        "gate_outcome": gate.get("overall_outcome") if gate else ("BASELINE" if rid == "v1.0" else "NOT_EVALUATED"),
        "ota_eligible": bool(gate.get("ota_eligible")) if gate else False,
        "rxswin_impact": bool(gate.get("rxswin_impact")) if gate else False,
        "recorded_variant_runs": [r.get("variant_id") for r in runs],
    }


@router.get("/releases")
def list_releases():
    items = [_enrich_release(r) for r in _releases.values()]
    return {"releases": items, "total": len(items)}


@router.post("/releases", status_code=201)
def register_release(req: RegisterReleaseRequest):
    rec = {
        "release_id": req.release_id,
        "description": req.description,
        "app_versions": req.app_versions,
        "created_by": req.created_by,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    _releases[req.release_id] = rec
    return _enrich_release(rec)


@router.get("/releases/{release_id}")
def get_release(release_id: str):
    rel = _releases.get(release_id)
    if not rel:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")
    return {
        **_enrich_release(rel),
        "gate": _load_gate_for_release(release_id),
        "runs_count": len(_load_runs_for_release(release_id)),
    }


@router.get("/releases/{release_id}/dossier")
def export_release_dossier(
    release_id: str,
    format: str = Query(default="json", pattern="^(json|html|pdf)$"),
    reviewer: str = Query(default="Homologation Reviewer"),
):
    """Spec §6 & M7-FR6: One-click UNECE R156 Release Evidence Dossier export in json | html | pdf."""
    dossier = assemble_dossier_json(release_id, reviewer=reviewer)

    if format == "json":
        return JSONResponse(content=dossier)

    if format == "html":
        html_str = render_dossier_html(dossier)
        return HTMLResponse(content=html_str)

    if format == "pdf":
        pdf_bytes = render_dossier_pdf(dossier)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="CORA_R156_Dossier_{release_id}.pdf"'
            },
        )

    raise HTTPException(status_code=400, detail="format must be json, html, or pdf")


@router.get("/metrics")
def get_measured_metrics():
    """Spec M7-FR7: Measured boot time, run wall time, and cost per release run."""
    return collect_measured_metrics()
