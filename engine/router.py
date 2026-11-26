"""
Module 5 Test, Equivalence & Release Gate REST API (Spec §6).
Endpoints:
  - POST /v1/runs                                       (start live test runs across variants)
  - GET  /v1/runs                                       (list recorded runs)
  - GET  /v1/runs/{run_id}                              (run status, results, traces, evidence links)
  - GET  /v1/releases/{id}/equivalence?baseline={rid}   (step-by-step equivalence report)
  - POST /v1/releases/{id}/gate?baseline={rid}          (idempotent per-variant gate decision + RXSWIN-impact)
  - GET  /v1/components                                 (software component register)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from engine.differ import build_equivalence_report
from engine.gate import load_component_register, release_gate
from engine.models import StartRunRequest
from engine.runner import scenario_runner

router = APIRouter(prefix="/v1", tags=["M5 Test, Equivalence & Release Gate"])


@router.get("/components")
def get_components():
    return {"components": load_component_register()}


@router.post("/runs")
def start_runs(req: StartRunRequest):
    """Runs live suites in parallel across all ONLINE target variants for a release."""
    try:
        runs = scenario_runner.run_release_across_variants(
            release_id=req.release_id,
            target_variants=req.variants,
            scenarios=req.scenarios,
        )
        return {
            "release_id": req.release_id,
            "runs": [r.model_dump() for r in runs],
            "total": len(runs),
        }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/runs")
def list_runs(release_id: str | None = None):
    runs = list(scenario_runner.runs.values())
    if release_id:
        runs = [r for r in runs if r.release_id == release_id]
    return {"runs": [r.model_dump() for r in runs], "total": len(runs)}


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    run = scenario_runner.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run.model_dump()


@router.get("/releases/{release_id}/equivalence")
def get_equivalence_report(
    release_id: str,
    baseline: str = Query(default="v1.0", description="Baseline release ID to diff against"),
):
    base_runs = scenario_runner.latest_runs_by_variant(baseline)
    cand_runs = scenario_runner.latest_runs_by_variant(release_id)
    if not base_runs:
        raise HTTPException(status_code=404, detail=f"No runs recorded for baseline release '{baseline}'")
    if not cand_runs:
        raise HTTPException(status_code=404, detail=f"No runs recorded for candidate release '{release_id}'")

    report = build_equivalence_report(base_runs, cand_runs, baseline, release_id)
    return report.model_dump()


@router.post("/releases/{release_id}/gate")
def evaluate_release_gate(
    release_id: str,
    baseline: str = Query(default="v1.0", description="Baseline release ID"),
):
    base_runs = scenario_runner.latest_runs_by_variant(baseline)
    cand_runs = scenario_runner.latest_runs_by_variant(release_id)
    if not cand_runs:
        raise HTTPException(status_code=404, detail=f"No runs recorded for release '{release_id}'")

    report = build_equivalence_report(base_runs, cand_runs, baseline, release_id)
    decision = release_gate.evaluate(release_id, baseline, cand_runs, report)
    return decision
