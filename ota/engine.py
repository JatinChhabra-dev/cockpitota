"""
Module 4 Staged OTA Rollout Engine & R156 Per-Vehicle Update Ledger (Spec §4 M4-FR1..FR6).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from ota.agent import VehicleUpdateAgent
from ota.hawkbit_client import HawkBitAdapter
from ota.models import (
    Campaign,
    CampaignStatus,
    CreateCampaignRequest,
    RolloutGroup,
    UpdateOutcome,
    UpdateRecord,
)
from ota.signing import sign_artefact

logger = logging.getLogger("ota.engine")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_DIST_DIR = os.path.join(ROOT_DIR, "apps", "dist")
EVIDENCE_DIR = os.path.join(ROOT_DIR, "evidence")
LEDGER_FILE = os.path.join(EVIDENCE_DIR, "ota_ledger.json")

_GEAR_STR_TO_INT = {
    "GEAR_UNKNOWN": 0,
    "GEAR_NEUTRAL": 1,
    "GEAR_REVERSE": 2,
    "GEAR_PARK": 4,
    "GEAR_DRIVE": 8,
}


class OtaRolloutEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self.hawkbit = HawkBitAdapter()
        self.vehicles: Dict[str, VehicleUpdateAgent] = {}
        self.campaigns: Dict[str, Campaign] = {}
        self.campaign_records: Dict[str, Dict[str, UpdateRecord]] = {}  # campaign_id -> {vehicle_id -> UpdateRecord}
        self.ledger: List[UpdateRecord] = []  # append-only R156 ledger

        self._init_default_10_vehicle_fleet()

    def _init_default_10_vehicle_fleet(self):
        """
        Initializes the 10-vehicle virtual OTA rollout fleet (Spec M1-FR7 & M4-FR1: 10% = 1 of 10).
        Vehicles 1..10 span VAR-A (4), VAR-B (3), VAR-C (3) with fictional ZFA VINs.
        """
        variant_pattern = [
            "VAR-A", "VAR-A", "VAR-A", "VAR-A",
            "VAR-B", "VAR-B", "VAR-B",
            "VAR-C", "VAR-C", "VAR-C",
        ]
        for idx, vid in enumerate(variant_pattern, start=1):
            veh_id = f"veh-{idx:02d}"
            vin = f"ZFA{vid.replace('-', '')}00{idx:05d}"
            self.vehicles[veh_id] = VehicleUpdateAgent(
                vehicle_id=veh_id,
                vin_like=vin,
                variant_id=vid,
            )

    def sync_live_fleet_instances(self):
        """
        Syncs currently ONLINE AAOS ADB instances from Fleet Manager onto the OTA fleet
        and removes any previously-bound ADB instances that have since been stopped.
        """
        try:
            from fleet.manager import _instances, _lock as fleet_lock
            from fleet.models import InstanceStatus
            from ota.agent import read_installed_version

            with fleet_lock:
                live = [i for i in _instances.values() if i.status == InstanceStatus.ONLINE and i.adb_serial]
                live_ids = {i.instance_id for i in live}

            with self._lock:
                # Remove stale ADB-backed instances that are no longer ONLINE
                stale_ids = [
                    vid for vid, veh in self.vehicles.items()
                    if veh.adb_serial is not None and vid not in live_ids
                ]
                for sid in stale_ids:
                    self.vehicles.pop(sid, None)

                # Add / refresh active ONLINE ADB instances
                for inst in live:
                    if inst.instance_id not in self.vehicles:
                        ev_ver = read_installed_version(inst.adb_serial, "com.aurelia.ev")
                        rv_ver = read_installed_version(inst.adb_serial, "com.aurelia.rearview")
                        self.vehicles[inst.instance_id] = VehicleUpdateAgent(
                            vehicle_id=inst.instance_id,
                            vin_like=inst.vin_like,
                            variant_id=inst.variant_id,
                            adb_serial=inst.adb_serial,
                            initial_versions={
                                "com.aurelia.ev": ev_ver,
                                "com.aurelia.rearview": rv_ver,
                            },
                        )
                    else:
                        self.vehicles[inst.instance_id].adb_serial = inst.adb_serial
        except Exception:
            pass

    def _persist_ledger(self):
        try:
            os.makedirs(EVIDENCE_DIR, exist_ok=True)
            with open(LEDGER_FILE, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in self.ledger], f, indent=2)
        except Exception as exc:
            logger.warning("Failed to persist OTA ledger: %s", exc)

    def list_vehicles(self, mode: str = "all") -> List[dict]:
        self.sync_live_fleet_instances()
        with self._lock:
            out = []
            for v in self.vehicles.values():
                is_live = v.adb_serial is not None
                if mode == "live" and not is_live:
                    continue
                if mode == "virtual" and is_live:
                    continue
                pre = v.get_preconditions()
                out.append({
                    "vehicle_id": v.vehicle_id,
                    "vin_like": v.vin_like,
                    "variant_id": v.variant_id,
                    "adb_serial": v.adb_serial,
                    "mode": "LIVE_ADB" if is_live else "VIRTUAL_HEADLESS",
                    "current_versions": v.current_versions,
                    "preconditions": pre.model_dump(),
                })
            return out

    def update_vehicle_sim_state(
        self,
        vehicle_id: str,
        gear: Optional[str] = None,
        speed_kmh: Optional[float] = None,
        parking_brake: Optional[bool] = None,
        soc_percent: Optional[float] = None,
    ) -> dict:
        self.sync_live_fleet_instances()
        with self._lock:
            veh = self.vehicles.get(vehicle_id)
            if not veh:
                raise KeyError(f"Vehicle '{vehicle_id}' not found")
            if gear is not None:
                veh.sim_gear = _GEAR_STR_TO_INT.get(gear.upper(), 4)
            if speed_kmh is not None:
                veh.sim_speed_ms = round(speed_kmh / 3.6, 2)
            if parking_brake is not None:
                veh.sim_parking_brake = parking_brake
            if soc_percent is not None:
                veh.sim_soc_percent = soc_percent

            # If bound to live ADB, also inject into VHAL so emulator stays synced
            if veh.adb_serial:
                try:
                    from fleet.manager import _get_injector
                    inj = _get_injector(veh.adb_serial)
                    if gear is not None:
                        inj.inject_vss("Vehicle.Powertrain.Transmission.SelectedGear", gear)
                    if speed_kmh is not None:
                        inj.inject_vss("Vehicle.Speed", speed_kmh)
                    if parking_brake is not None:
                        inj.inject_vss("Vehicle.Chassis.ParkingBrake.IsEngaged", parking_brake)
                    if soc_percent is not None:
                        inj.inject_vss("Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed", soc_percent)
                except Exception as exc:
                    logger.warning("Failed to sync sim state to live ADB %s: %s", veh.adb_serial, exc)

            return {
                "vehicle_id": vehicle_id,
                "preconditions": veh.get_preconditions().model_dump(),
            }

    def create_campaign(self, req: CreateCampaignRequest) -> Campaign:
        """
        Creates a staged 2-group OTA rollout campaign (10% canary -> 100% fleet).
        Enforces Gate -> hawkBit adapter check: refuses creation if gate_passed is False.
        """
        if not req.gate_passed:
            raise ValueError("RELEASE_GATE_BLOCKED: Cannot create OTA campaign for a release that failed the gate")

        self.sync_live_fleet_instances()
        apk_path = os.path.join(APPS_DIST_DIR, req.apk_filename)
        if not os.path.isfile(apk_path):
            raise FileNotFoundError(f"APK artefact not found: {apk_path}. Run apps/build_apks.ps1 first.")

        sha256_hex, sig_hex = sign_artefact(apk_path)
        if req.tamper_test:
            # Deliberately corrupt signature to test M4-FR3 rejection
            sig_hex = "00" * 32

        with self._lock:
            if req.vehicle_ids:
                target_ids = [vid for vid in req.vehicle_ids if vid in self.vehicles]
            elif req.target_mode == "live":
                target_ids = [vid for vid, veh in self.vehicles.items() if veh.adb_serial is not None]
                if not target_ids:
                    raise ValueError("No live ONLINE AAOS cockpits found. Launch VAR-A/B/C in Virtual Fleet (M1) first.")
            else:
                target_ids = [f"veh-{i:02d}" for i in range(1, 11) if f"veh-{i:02d}" in self.vehicles]

            if not target_ids:
                raise ValueError("No valid target vehicles found for campaign")

            # M4-FR1: Group 1 = 10% (min 1 vehicle), Group 2 = remaining (100% total)
            canary_count = max(1, round(len(target_ids) * 0.10))
            group1_ids = target_ids[:canary_count]
            group2_ids = target_ids[canary_count:]

            groups = [
                RolloutGroup(
                    group_index=1,
                    name="Group 1 — 10% Canary",
                    percentage=10,
                    target_vehicle_ids=group1_ids,
                    status="RUNNING" if req.auto_start else "WAITING",
                    success_threshold_pct=100,
                )
            ]
            if group2_ids:
                groups.append(
                    RolloutGroup(
                        group_index=2,
                        name="Group 2 — 100% Fleet",
                        percentage=100,
                        target_vehicle_ids=group2_ids,
                        status="WAITING",
                        success_threshold_pct=100,
                    )
                )

            now_iso = datetime.utcnow().isoformat() + "Z"
            campaign_id = f"camp-{uuid.uuid4().hex[:8]}"

            # Sync targets & create staged rollout in Eclipse hawkBit 1.0 (or LOCAL_MIRROR if Docker offline)
            target_objs = [
                {
                    "vehicle_id": vid,
                    "variant_id": self.vehicles[vid].variant_id,
                    "vin_like": self.vehicles[vid].vin_like,
                }
                for vid in target_ids
            ]
            self.hawkbit.sync_targets(target_objs)
            hb_rollout_id, hb_mode = self.hawkbit.create_staged_rollout(
                campaign_id=campaign_id,
                release_id=req.release_id,
                package_name=req.package_name,
                target_version=req.target_version,
                vehicle_ids=target_ids,
            )

            campaign = Campaign(
                campaign_id=campaign_id,
                release_id=req.release_id,
                apk_filename=req.apk_filename,
                package_name=req.package_name,
                target_version=req.target_version,
                artefact_sha256=sha256_hex,
                signature_hex=sig_hex,
                hawkbit_rollout_id=hb_rollout_id,
                hawkbit_mode=hb_mode,
                status=CampaignStatus.RUNNING if req.auto_start else CampaignStatus.CREATED,
                groups=groups,
                created_at=now_iso,
                updated_at=now_iso,
            )

            self.campaigns[campaign_id] = campaign
            self.campaign_records[campaign_id] = {}

            for g in groups:
                for vid in g.target_vehicle_ids:
                    veh = self.vehicles[vid]
                    rec = UpdateRecord(
                        record_id=f"upd-{uuid.uuid4().hex[:8]}",
                        vehicle_id=vid,
                        vin_like=veh.vin_like,
                        variant_id=veh.variant_id,
                        campaign_id=campaign_id,
                        release_id=req.release_id,
                        group_index=g.group_index,
                        started_at=now_iso,
                    )
                    self.campaign_records[campaign_id][vid] = rec
                    self.ledger.append(rec)

            self._persist_ledger()

        if req.auto_start:
            self.tick_campaign(campaign_id)

        return self.campaigns[campaign_id]

    def tick_campaign(self, campaign_id: str) -> Campaign:
        """
        Executes one rollout evaluation cycle:
          - Evaluates all PENDING/DEFERRED vehicles in RUNNING groups
          - Auto-advances Group 1 -> Group 2 when Group 1 hits >= 100% INSTALLED (M4-FR1)
          - Updates campaign status to FINISHED or FAILED when all active groups conclude
        """
        with self._lock:
            campaign = self.campaigns.get(campaign_id)
            if not campaign:
                raise KeyError(f"Campaign '{campaign_id}' not found")
            if campaign.status not in (CampaignStatus.RUNNING, CampaignStatus.CREATED):
                return campaign

            campaign.status = CampaignStatus.RUNNING
            apk_path = os.path.join(APPS_DIST_DIR, campaign.apk_filename)
            rollback_apk = os.path.join(APPS_DIST_DIR, "aurelia-ev-v1.0.apk")
            recs = self.campaign_records[campaign_id]

            for idx, group in enumerate(campaign.groups):
                if group.status != "RUNNING":
                    continue

                for vid in group.target_vehicle_ids:
                    rec = recs[vid]
                    if rec.outcome in (UpdateOutcome.INSTALLED, UpdateOutcome.REJECTED, UpdateOutcome.ROLLED_BACK, UpdateOutcome.FAILED):
                        continue
                    veh = self.vehicles[vid]
                    veh.process_update(
                        record=rec,
                        apk_path=apk_path,
                        package_name=campaign.package_name,
                        target_version=campaign.target_version,
                        expected_sha256=campaign.artefact_sha256,
                        expected_signature=campaign.signature_hex,
                        rollback_apk_path=rollback_apk,
                    )

                # Recompute group counts
                g_recs = [recs[vid] for vid in group.target_vehicle_ids]
                group.installed_count = sum(1 for r in g_recs if r.outcome == UpdateOutcome.INSTALLED)
                group.deferred_count = sum(1 for r in g_recs if r.outcome == UpdateOutcome.DEFERRED)
                group.failed_count = sum(1 for r in g_recs if r.outcome in (UpdateOutcome.REJECTED, UpdateOutcome.FAILED, UpdateOutcome.ROLLED_BACK))

                total = len(g_recs)
                if group.failed_count > 0:
                    group.status = "FAILED"
                    campaign.status = CampaignStatus.FAILED
                    break

                if total > 0 and group.installed_count == total:
                    group.status = "FINISHED"
                    # M4-FR1: Auto-advance to next group on 100% success in Group 1
                    if idx + 1 < len(campaign.groups):
                        next_group = campaign.groups[idx + 1]
                        if next_group.status == "WAITING":
                            next_group.status = "RUNNING"
                            logger.info("[CAMPAIGN %s] Group %d reached 100%% success — auto-advancing to %s",
                                        campaign_id, group.group_index, next_group.name)

            # Check if all groups finished
            if campaign.status == CampaignStatus.RUNNING and all(g.status == "FINISHED" for g in campaign.groups):
                campaign.status = CampaignStatus.FINISHED

            campaign.updated_at = datetime.utcnow().isoformat() + "Z"
            self._persist_ledger()
            return campaign

    def pause_campaign(self, campaign_id: str) -> Campaign:
        with self._lock:
            c = self.campaigns.get(campaign_id)
            if not c:
                raise KeyError(f"Campaign '{campaign_id}' not found")
            c.status = CampaignStatus.PAUSED
            for g in c.groups:
                if g.status == "RUNNING":
                    g.status = "PAUSED"
            c.updated_at = datetime.utcnow().isoformat() + "Z"
            self.hawkbit.pause_rollout(c.hawkbit_rollout_id, c.hawkbit_mode)
            return c

    def resume_campaign(self, campaign_id: str) -> Campaign:
        with self._lock:
            c = self.campaigns.get(campaign_id)
            if not c:
                raise KeyError(f"Campaign '{campaign_id}' not found")
            if c.status == CampaignStatus.PAUSED:
                c.status = CampaignStatus.RUNNING
                for g in c.groups:
                    if g.status == "PAUSED":
                        g.status = "RUNNING"
                c.updated_at = datetime.utcnow().isoformat() + "Z"
                self.hawkbit.resume_rollout(c.hawkbit_rollout_id, c.hawkbit_mode)
        return self.tick_campaign(campaign_id)

    def cancel_campaign(self, campaign_id: str) -> Campaign:
        with self._lock:
            c = self.campaigns.get(campaign_id)
            if not c:
                raise KeyError(f"Campaign '{campaign_id}' not found")
            c.status = CampaignStatus.CANCELED
            for g in c.groups:
                if g.status in ("WAITING", "RUNNING", "PAUSED"):
                    g.status = "CANCELED"
            c.updated_at = datetime.utcnow().isoformat() + "Z"
            return c

    def get_campaign_detail(self, campaign_id: str) -> dict:
        with self._lock:
            c = self.campaigns.get(campaign_id)
            if not c:
                raise KeyError(f"Campaign '{campaign_id}' not found")
            recs = list(self.campaign_records.get(campaign_id, {}).values())
            return {
                "campaign": c.model_dump(),
                "records": [r.model_dump() for r in recs],
            }

    def get_vehicle_ledger(self, vehicle_id: str) -> List[dict]:
        with self._lock:
            return [r.model_dump() for r in self.ledger if r.vehicle_id == vehicle_id]


# Singleton engine instance shared across Fleet Manager & M5/M7
ota_engine = OtaRolloutEngine()
