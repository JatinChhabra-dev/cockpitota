"""
Module 4 OTA Rollout & Vehicle Ledger REST API (Spec §6).
Endpoints:
  - POST /v1/campaigns
  - GET  /v1/campaigns
  - GET  /v1/campaigns/{id}
  - POST /v1/campaigns/{id}/tick
  - POST /v1/campaigns/{id}/pause
  - POST /v1/campaigns/{id}/resume
  - POST /v1/campaigns/{id}/cancel
  - GET  /v1/vehicles
  - GET  /v1/vehicles/{id}/ledger
  - POST /v1/vehicles/{id}/state
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ota.engine import ota_engine
from ota.models import CreateCampaignRequest, VehicleSimStateRequest

router = APIRouter(prefix="/v1", tags=["M4 OTA Rollout & Vehicle Ledger"])


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
def create_campaign(req: CreateCampaignRequest):
    try:
        campaign = ota_engine.create_campaign(req)
        return ota_engine.get_campaign_detail(campaign.campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/campaigns")
def list_campaigns():
    campaigns = [c.model_dump() for c in ota_engine.campaigns.values()]
    return {
        "hawkbit_live": ota_engine.hawkbit.is_available(),
        "campaigns": campaigns,
        "total": len(campaigns),
    }


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str):
    try:
        return ota_engine.get_campaign_detail(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/campaigns/{campaign_id}/tick")
def tick_campaign(campaign_id: str):
    try:
        ota_engine.tick_campaign(campaign_id)
        return ota_engine.get_campaign_detail(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: str):
    try:
        ota_engine.pause_campaign(campaign_id)
        return ota_engine.get_campaign_detail(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/campaigns/{campaign_id}/resume")
def resume_campaign(campaign_id: str):
    try:
        ota_engine.resume_campaign(campaign_id)
        return ota_engine.get_campaign_detail(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id: str):
    try:
        ota_engine.cancel_campaign(campaign_id)
        return ota_engine.get_campaign_detail(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/vehicles")
def list_vehicles(mode: str = "all"):
    vehicles = ota_engine.list_vehicles(mode=mode)
    return {"vehicles": vehicles, "total": len(vehicles), "mode": mode}


@router.get("/vehicles/{vehicle_id}/ledger")
def get_vehicle_ledger(vehicle_id: str):
    records = ota_engine.get_vehicle_ledger(vehicle_id)
    return {"vehicle_id": vehicle_id, "records": records, "total": len(records)}


@router.post("/vehicles/{vehicle_id}/state")
def set_vehicle_state(vehicle_id: str, body: VehicleSimStateRequest):
    try:
        return ota_engine.update_vehicle_sim_state(
            vehicle_id=vehicle_id,
            gear=body.gear,
            speed_kmh=body.speed_kmh,
            parking_brake=body.parking_brake,
            soc_percent=body.soc_percent,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
