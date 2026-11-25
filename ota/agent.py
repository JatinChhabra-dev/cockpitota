"""
Module 4 Update Agent State Machine (Spec §4 Figure 2, M4-FR2..FR5).
State machine:
  IDLE -> POLLING -> DOWNLOADING -> VERIFYING -> WAIT_PRECOND -> INSTALLING -> REPORTING
                                        |-> REJECTED (hash/signature mismatch)
                                                       |-> DEFERRED (not parked or SoC < 30%)
                                                                     |-> ROLLED_BACK (install failure)
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fleet.avd_backend import _adb_path
from ota.models import AgentState, PreconditionSnapshot, UpdateOutcome, UpdateRecord
from ota.signing import verify_artefact

logger = logging.getLogger("ota.agent")

# VHAL property IDs for M4-FR2 preconditions
PROP_GEAR_SELECTION = 289408000
PROP_PERF_VEHICLE_SPEED = 291504647
PROP_PARKING_BRAKE_ON = 287310850
PROP_EV_BATTERY_LEVEL = 291504905

GEAR_PARK = 4
BATTERY_CAPACITY_WH = 75000.0
MIN_SOC_PERCENT = 30.0


def _adb_run(serial: str, args: List[str], timeout: float = 20.0) -> Tuple[int, str]:
    cmd = [_adb_path(), "-s", serial] + args
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return res.returncode, (res.stdout + "\n" + res.stderr).strip()


def read_live_vhal_float(serial: str, prop_id: int, default: float) -> float:
    rc, out = _adb_run(serial, ["shell", "cmd", "car_service", "get-property-value", str(prop_id), "0"], timeout=5.0)
    if rc == 0:
        m = re.search(r"value=([0-9.\-]+)", out)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return default


def read_live_vhal_int(serial: str, prop_id: int, default: int) -> int:
    rc, out = _adb_run(serial, ["shell", "cmd", "car_service", "get-property-value", str(prop_id), "0"], timeout=5.0)
    if rc == 0:
        m = re.search(r"value=([0-9\-]+)", out)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return default


def read_installed_version(serial: str, package_name: str) -> str:
    """Reads currently installed versionName of an Android package on a live AAOS cockpit."""
    rc, out = _adb_run(serial, ["shell", "dumpsys", "package", package_name], timeout=8.0)
    if rc == 0:
        m = re.search(r"versionName=([^\s]+)", out)
        if m:
            return m.group(1).strip()
    return "uninstalled"


def evaluate_preconditions(
    gear: int,
    speed_ms: float,
    parking_brake: bool,
    soc_percent: float,
) -> PreconditionSnapshot:
    """
    Spec M4-FR2:
      Install ONLY when parked (gear == PARK and speed == 0) AND battery SoC >= 30%.
    """
    reasons: List[str] = []
    if gear != GEAR_PARK:
        reasons.append(f"GEAR_NOT_PARK (gear={gear}, required=4)")
    if abs(speed_ms) > 0.1:
        reasons.append(f"VEHICLE_MOVING (speed={round(speed_ms * 3.6, 1)} km/h, required=0)")
    if soc_percent < MIN_SOC_PERCENT:
        reasons.append(f"LOW_BATTERY_SOC (soc={round(soc_percent, 1)}%, required>=30%)")

    return PreconditionSnapshot(
        gear=gear,
        speed_ms=speed_ms,
        parking_brake=parking_brake,
        soc_percent=soc_percent,
        passed=(len(reasons) == 0),
        defer_reasons=reasons,
    )


class VehicleUpdateAgent:
    """
    Executes the OTA Update Agent state machine for a single vehicle
    (either a live AAOS emulator reachable via ADB or a lightweight headless virtual vehicle).
    """

    def __init__(
        self,
        vehicle_id: str,
        vin_like: str,
        variant_id: str,
        adb_serial: Optional[str] = None,
        initial_versions: Optional[Dict[str, str]] = None,
    ):
        self.vehicle_id = vehicle_id
        self.vin_like = vin_like
        self.variant_id = variant_id
        self.adb_serial = adb_serial
        self.current_versions: Dict[str, str] = dict(initial_versions or {"com.aurelia.ev": "1.0.0", "com.aurelia.rearview": "1.0.0"})

        # Simulated state (used for lightweight headless fleet vehicles; live ADB devices read real VHAL)
        self.sim_gear: int = GEAR_PARK
        self.sim_speed_ms: float = 0.0
        self.sim_parking_brake: bool = True
        self.sim_soc_percent: float = 80.0

    def get_preconditions(self) -> PreconditionSnapshot:
        if self.adb_serial:
            gear = read_live_vhal_int(self.adb_serial, PROP_GEAR_SELECTION, self.sim_gear)
            speed_ms = read_live_vhal_float(self.adb_serial, PROP_PERF_VEHICLE_SPEED, self.sim_speed_ms)
            brake = read_live_vhal_int(self.adb_serial, PROP_PARKING_BRAKE_ON, 1 if self.sim_parking_brake else 0) == 1
            wh = read_live_vhal_float(self.adb_serial, PROP_EV_BATTERY_LEVEL, (self.sim_soc_percent / 100.0) * BATTERY_CAPACITY_WH)
            soc = round((wh / BATTERY_CAPACITY_WH) * 100.0, 1)
            return evaluate_preconditions(gear, speed_ms, brake, soc)
        return evaluate_preconditions(self.sim_gear, self.sim_speed_ms, self.sim_parking_brake, self.sim_soc_percent)

    def process_update(
        self,
        record: UpdateRecord,
        apk_path: str,
        package_name: str,
        target_version: str,
        expected_sha256: str,
        expected_signature: str,
        rollback_apk_path: Optional[str] = None,
    ) -> UpdateRecord:
        """
        Runs one agent evaluation cycle on the given UpdateRecord:
          POLLING -> DOWNLOADING -> VERIFYING -> WAIT_PRECOND -> INSTALLING -> REPORTING
        """
        now_iso = lambda: datetime.utcnow().isoformat() + "Z"

        # Capture pre-update versions (M4-FR4)
        if not record.pre_versions:
            if self.adb_serial:
                self.current_versions[package_name] = read_installed_version(self.adb_serial, package_name)
            record.pre_versions = dict(self.current_versions)

        # 1. VERIFYING (M4-FR3: SHA-256 + Signature check)
        record.agent_state = AgentState.VERIFYING
        ok, reason = verify_artefact(apk_path, expected_sha256, expected_signature)
        record.artefact_sha256 = expected_sha256
        record.signature_verified = ok
        if not ok:
            record.agent_state = AgentState.REJECTED
            record.outcome = UpdateOutcome.REJECTED
            record.failure_reason = reason
            record.post_versions = dict(record.pre_versions)
            record.ended_at = now_iso()
            logger.warning("[AGENT %s] REJECTED artefact: %s", self.vehicle_id, reason)
            return record

        # 2. WAIT_PRECOND (M4-FR2: Parked + SoC >= 30%)
        record.agent_state = AgentState.WAIT_PRECOND
        pre = self.get_preconditions()
        if not pre.passed:
            record.outcome = UpdateOutcome.DEFERRED
            record.defer_reasons = pre.defer_reasons
            logger.info("[AGENT %s] DEFERRED: %s", self.vehicle_id, "; ".join(pre.defer_reasons))
            return record

        # 3. INSTALLING
        record.agent_state = AgentState.INSTALLING
        record.defer_reasons = []
        if self.adb_serial:
            rc, out = _adb_run(self.adb_serial, ["install", "-r", "-d", "-g", apk_path], timeout=60.0)
            if rc != 0 or "Success" not in out:
                logger.error("[AGENT %s] ADB install failed: %s", self.vehicle_id, out)
                # M4-FR5: Rollback on install failure
                if rollback_apk_path and os.path.isfile(rollback_apk_path):
                    _adb_run(self.adb_serial, ["install", "-r", "-d", "-g", rollback_apk_path], timeout=60.0)
                    record.agent_state = AgentState.ROLLED_BACK
                    record.outcome = UpdateOutcome.ROLLED_BACK
                else:
                    record.outcome = UpdateOutcome.FAILED
                record.failure_reason = f"INSTALL_FAILED: {out[:200]}"
                record.post_versions = dict(record.pre_versions)
                record.ended_at = now_iso()
                return record

            installed_ver = read_installed_version(self.adb_serial, package_name)
            self.current_versions[package_name] = installed_ver
            # Auto-relaunch Aurelia EV after OTA install so the updated UI appears immediately
            if package_name == "com.aurelia.ev":
                _adb_run(self.adb_serial, ["shell", "am", "start", "-n", "com.aurelia.ev/.MainActivity"], timeout=10.0)
        else:
            # Lightweight virtual vehicle install
            self.current_versions[package_name] = target_version

        # 4. REPORTING
        record.agent_state = AgentState.REPORTING
        record.post_versions = dict(self.current_versions)
        record.outcome = UpdateOutcome.INSTALLED
        record.ended_at = now_iso()
        logger.info(
            "[AGENT %s] INSTALLED %s: %s -> %s",
            self.vehicle_id,
            package_name,
            record.pre_versions.get(package_name),
            record.post_versions.get(package_name),
        )
        return record
