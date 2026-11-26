"""
Module 5 Real Live Scenario Runner & Check Suites (Spec §4 M5-FR1..FR3, M5-FR8, §8.1).
Executes real AAOS suites against live ONLINE emulators via ADB + VhalInjector,
records real TraceSteps (UI tree, z-order, VHAL, screenshots, logcat), and exports
JUnit XML + JSON trace bundles into evidence/runs/<run_id>/.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from fleet.avd_backend import _adb_path, ensure_demo_apps
from engine.models import RunRecord, TestResult, TestStatus, TraceStep
from engine.trace import clear_logcat, record_trace_step

logger = logging.getLogger("engine.runner")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS_DIR = os.path.join(ROOT_DIR, "evidence", "runs")


def _adb_shell(serial: str, args: List[str], timeout: float = 12.0) -> str:
    cmd = [_adb_path(), "-s", serial, "shell"] + args
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return ((res.stdout or "") + "\n" + (res.stderr or "")).strip()


def _write_junit_xml(run: RunRecord, out_path: str):
    suite_el = ET.Element("testsuite", {
        "name": f"CORA_{run.release_id}_{run.variant_id}",
        "tests": str(len(run.results)),
        "failures": str(sum(1 for r in run.results if r.status in (TestStatus.FAIL, TestStatus.FLAKY))),
        "time": f"{run.wall_time_seconds:.2f}",
    })
    for r in run.results:
        tc = ET.SubElement(suite_el, "testcase", {
            "classname": f"{run.variant_id}.{r.suite}",
            "name": r.test_id,
            "time": f"{(r.timing_ms or 0) / 1000.0:.3f}",
        })
        if r.status == TestStatus.FAIL:
            fail = ET.SubElement(tc, "failure", {"message": r.message})
            fail.text = r.message
        elif r.status == TestStatus.FLAKY:
            fail = ET.SubElement(tc, "failure", {"type": "FLAKY", "message": f"Quarantined FLAKY: {r.message}"})
            fail.text = r.message
    ET.ElementTree(suite_el).write(out_path, encoding="utf-8", xml_declaration=True)


class ScenarioRunner:
    def __init__(self):
        self.runs: Dict[str, RunRecord] = {}

    def _run_with_flaky_quarantine(
        self,
        run_id: str,
        test_id: str,
        suite: str,
        scenario_id: str,
        check_fn: Callable[[], Tuple[bool, str, Optional[float], List[str]]],
        allow_retry: bool = True,
    ) -> TestResult:
        """
        Executes a real check; if it fails on attempt 1 and passes on retry,
        marks status=FLAKY (not PASS) per Spec M5-FR8.
        """
        ok, msg, timing_ms, uris = check_fn()
        if ok:
            return TestResult(
                result_id=f"res-{uuid.uuid4().hex[:8]}",
                run_id=run_id,
                test_id=test_id,
                suite=suite,
                scenario_id=scenario_id,
                status=TestStatus.PASS,
                message=msg,
                timing_ms=timing_ms,
                retries=0,
                evidence_uris=uris,
            )

        if allow_retry:
            time.sleep(0.5)
            ok2, msg2, timing2, uris2 = check_fn()
            if ok2:
                return TestResult(
                    result_id=f"res-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    test_id=test_id,
                    suite=suite,
                    scenario_id=scenario_id,
                    status=TestStatus.FLAKY,
                    message=f"Failed first attempt ({msg}), passed on retry ({msg2})",
                    timing_ms=timing2,
                    retries=1,
                    evidence_uris=uris + uris2,
                )

        return TestResult(
            result_id=f"res-{uuid.uuid4().hex[:8]}",
            run_id=run_id,
            test_id=test_id,
            suite=suite,
            scenario_id=scenario_id,
            status=TestStatus.FAIL,
            message=msg,
            timing_ms=timing_ms,
            retries=1 if allow_retry else 0,
            evidence_uris=uris,
        )

    def execute_variant_run(
        self,
        release_id: str,
        variant_id: str,
        instance_id: str,
        adb_serial: str,
        scenarios: List[str],
    ) -> RunRecord:
        """
        Executes all selected scenarios live on a single ONLINE AAOS emulator.
        """
        from fleet.manager import _get_injector

        t0 = time.perf_counter()
        run_id = f"run-{release_id.replace('.', '_')}-{variant_id.lower().replace('-', '')}-{uuid.uuid4().hex[:6]}"
        run_dir = os.path.join(RUNS_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)

        run = RunRecord(
            run_id=run_id,
            release_id=release_id,
            variant_id=variant_id,
            instance_id=instance_id,
            adb_serial=adb_serial,
            scenarios=list(scenarios),
            status="RUNNING",
            started_at=datetime.utcnow().isoformat() + "Z",
        )
        self.runs[run_id] = run

        try:
            # 1. Install exact target release build & launch APP-1
            logger.info("[%s] Ensuring release %s on %s (%s)...", run_id, release_id, variant_id, adb_serial)
            ensure_demo_apps(adb_serial, release_id)
            time.sleep(1.5)

            inj = _get_injector(adb_serial)

            # Reset ALL 7 VHAL properties to a clean, deterministic parked baseline
            # (prevents state leakage between v1.0 -> v1.1 -> v1.1-fix runs)
            inj.inject_vss("Vehicle.Speed", 0.0)
            inj.inject_vss("Vehicle.Powertrain.Transmission.SelectedGear", "GEAR_PARK")
            inj.inject_vss("Vehicle.Chassis.ParkingBrake.IsEngaged", True)
            inj.inject_vss("Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed", 80.0)
            inj.inject_vss("Vehicle.Powertrain.TractionBattery.Charging.ChargePortFlap", False)
            inj.inject_vss("Vehicle.Powertrain.TractionBattery.Charging.IsChargingCableConnected", False)
            inj.set_hvac_temperature(21.5, row=49)
            _adb_shell(adb_serial, [
                "am", "broadcast",
                "-a", "com.aurelia.ev.ACTION_REMOTE_CLIMATE",
                "--ef", "temperature_c", "21.5",
                "-n", "com.aurelia.ev/.RemoteCommandReceiver",
            ])

            # Warm up APP-2 RearView process once (mirrors production AAOS persistent rear-view service)
            _adb_shell(adb_serial, ["am", "start", "-n", "com.aurelia.rearview/.RearViewActivity"])
            time.sleep(0.6)
            _adb_shell(adb_serial, ["am", "broadcast", "-a", "com.aurelia.rearview.ACTION_HIDE"])
            time.sleep(0.4)
            _adb_shell(adb_serial, ["am", "start", "-n", "com.aurelia.ev/.MainActivity"])
            time.sleep(0.9)

            # Capture initial parked home screen trace (used for UI & localisation equivalence diff!)
            t_home = record_trace_step(run_id, "BASELINE", "home_parked", variant_id, adb_serial, run_dir)
            run.traces.append(t_home)

            # ---------------------------------------------------------------
            # Suite 1: SC-01 UX Restrictions while moving (M5-FR2)
            # ---------------------------------------------------------------
            if "SC-01" in scenarios:
                def check_sc01() -> Tuple[bool, str, Optional[float], List[str]]:
                    ts0 = time.perf_counter()
                    inj.inject_vss("Vehicle.Powertrain.Transmission.SelectedGear", "GEAR_DRIVE")
                    inj.inject_vss("Vehicle.Speed", 50.0)
                    time.sleep(1.0)
                    step_move = record_trace_step(run_id, "SC-01", "driving_50kmh", variant_id, adb_serial, run_dir,
                                                  timing_ms=round((time.perf_counter() - ts0) * 1000, 1))
                    run.traces.append(step_move)

                    ux_banner = step_move.ui_nodes.get("com.aurelia.ev:id/banner_ux_restricted")
                    charge_input = step_move.ui_nodes.get("com.aurelia.ev:id/input_charge_note")
                    locked_ok = (ux_banner is not None) and (charge_input is None or not charge_input.enabled)

                    # Release back to parked 0 km/h
                    inj.inject_vss("Vehicle.Speed", 0.0)
                    inj.inject_vss("Vehicle.Powertrain.Transmission.SelectedGear", "GEAR_PARK")
                    time.sleep(0.8)
                    step_stop = record_trace_step(run_id, "SC-01", "stopped_0kmh", variant_id, adb_serial, run_dir)
                    run.traces.append(step_stop)

                    charge_input_parked = step_stop.ui_nodes.get("com.aurelia.ev:id/input_charge_note")
                    unlocked_ok = (charge_input_parked is None) or charge_input_parked.enabled

                    uris = [u for u in [step_move.screenshot_uri, step_stop.screenshot_uri] if u]
                    if locked_ok and unlocked_ok:
                        return True, "UX restrictions engaged at 50 km/h and released at 0 km/h", step_move.timing_ms, uris
                    return False, f"UX lock mismatch (banner={ux_banner is not None}, locked_ok={locked_ok}, unlocked_ok={unlocked_ok})", step_move.timing_ms, uris

                run.results.append(self._run_with_flaky_quarantine(
                    run_id, "ux_restrictions_engage_and_release", "ux_restriction", "SC-01", check_sc01
                ))

            # ---------------------------------------------------------------
            # Suite 2: SC-02 Park & Charge Functional Check
            # ---------------------------------------------------------------
            if "SC-02" in scenarios:
                def check_sc02() -> Tuple[bool, str, Optional[float], List[str]]:
                    ts0 = time.perf_counter()
                    inj.inject_vss("Vehicle.Powertrain.Transmission.SelectedGear", "GEAR_PARK")
                    inj.inject_vss("Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed", 80.0)
                    inj.inject_vss("Vehicle.Powertrain.TractionBattery.Charging.ChargePortFlap", True)
                    inj.inject_vss("Vehicle.Powertrain.TractionBattery.Charging.IsChargingCableConnected", True)
                    time.sleep(1.0)
                    step = record_trace_step(run_id, "SC-02", "charging_80pct", variant_id, adb_serial, run_dir,
                                             timing_ms=round((time.perf_counter() - ts0) * 1000, 1))
                    run.traces.append(step)

                    soc_node = step.ui_nodes.get("com.aurelia.ev:id/txt_soc_value")
                    port_node = step.ui_nodes.get("com.aurelia.ev:id/txt_charge_port_status")
                    cable_node = step.ui_nodes.get("com.aurelia.ev:id/txt_charge_cable_status")
                    ok = (
                        soc_node is not None and "80%" in soc_node.text
                        and port_node is not None and "OPEN" in port_node.text
                        and cable_node is not None and "CONNECTED" in cable_node.text
                    )
                    uris = [step.screenshot_uri] if step.screenshot_uri else []
                    detail = f"soc={soc_node.text if soc_node else 'N/A'}, port={port_node.text if port_node else 'N/A'}, cable={cable_node.text if cable_node else 'N/A'}"
                    return ok, detail, step.timing_ms, uris

                run.results.append(self._run_with_flaky_quarantine(
                    run_id, "ev_charging_state_display", "functional", "SC-02", check_sc02
                ))

            # ---------------------------------------------------------------
            # Suite 3: SC-03 Safety-Relevant Rear-View < 500 ms (M5-FR3)
            # ---------------------------------------------------------------
            if "SC-03" in scenarios:
                def check_sc03() -> Tuple[bool, str, Optional[float], List[str]]:
                    inj.inject_vss("Vehicle.Speed", 0.0)
                    inj.inject_vss("Vehicle.Powertrain.Transmission.SelectedGear", "GEAR_PARK")
                    time.sleep(0.5)
                    _adb_shell(adb_serial, ["am", "start", "-n", "com.aurelia.ev/.MainActivity"])
                    time.sleep(0.8)
                    _adb_shell(adb_serial, [
                        "am", "broadcast",
                        "-a", "com.aurelia.ev.ACTION_OPEN_CHARGING_MODAL",
                        "-n", "com.aurelia.ev/.RemoteCommandReceiver",
                    ])
                    time.sleep(0.9)

                    clear_logcat(adb_serial)
                    inj.inject_vss("Vehicle.Powertrain.Transmission.SelectedGear", "GEAR_REVERSE")
                    time.sleep(1.2)

                    step = record_trace_step(
                        run_id, "SC-03", "reverse_with_modal", variant_id, adb_serial, run_dir,
                        safety_relevant=True,
                    )

                    # Extract exact render latency from logcat (or fallback to real UI node txt_rearview_latency)
                    latency_ms: Optional[float] = None
                    defect_sig = False
                    for ln in step.logcat_excerpt:
                        m = re.search(r"RearViewActivity visible in (\d+)ms", ln)
                        if m:
                            latency_ms = float(m.group(1))
                        if "[DEFECT_M3_FR4]" in ln:
                            defect_sig = True
                    if latency_ms is None:
                        lat_node = step.ui_nodes.get("com.aurelia.rearview:id/txt_rearview_latency")
                        if lat_node:
                            m2 = re.search(r"RENDER LATENCY:\s*(\d+)\s*ms", lat_node.text)
                            if m2:
                                latency_ms = float(m2.group(1))
                    step.timing_ms = latency_ms
                    run.traces.append(step)

                    # Restore to PARK cleanly
                    inj.inject_vss("Vehicle.Powertrain.Transmission.SelectedGear", "GEAR_PARK")
                    time.sleep(0.6)

                    rv_on_top = "com.aurelia.rearview/.RearViewActivity" in step.top_activity
                    within_ceiling = (latency_ms is not None and latency_ms < 500.0)
                    uris = [step.screenshot_uri] if step.screenshot_uri else []

                    if rv_on_top and within_ceiling and not defect_sig:
                        return True, f"APP-2 RearView visible on top in {latency_ms}ms (<500ms)", latency_ms, uris
                    if defect_sig or not rv_on_top:
                        return False, f"SAFETY FAILURE: APP-2 suppressed (top={step.top_activity}, defect_log={defect_sig})", latency_ms, uris
                    return False, f"SAFETY TIMING FAILURE: APP-2 latency {latency_ms}ms exceeded 500ms ceiling", latency_ms, uris

                # Safety checks do not mask failures via retry
                run.results.append(self._run_with_flaky_quarantine(
                    run_id, "rearview_visible_within_500ms", "safety_display", "SC-03", check_sc03, allow_retry=False
                ))

            # ---------------------------------------------------------------
            # Suite 4: SC-04 Remote Climate Round-Trip
            # ---------------------------------------------------------------
            if "SC-04" in scenarios:
                def check_sc04() -> Tuple[bool, str, Optional[float], List[str]]:
                    ts0 = time.perf_counter()
                    inj.set_hvac_temperature(21.0, row=49)
                    _adb_shell(adb_serial, [
                        "am", "broadcast",
                        "-a", "com.aurelia.ev.ACTION_REMOTE_CLIMATE",
                        "--ef", "temperature_c", "21.0",
                        "-n", "com.aurelia.ev/.RemoteCommandReceiver",
                    ])
                    time.sleep(0.9)
                    step = record_trace_step(run_id, "SC-04", "remote_climate_21c", variant_id, adb_serial, run_dir,
                                             timing_ms=round((time.perf_counter() - ts0) * 1000, 1))
                    run.traces.append(step)
                    hvac_node = step.ui_nodes.get("com.aurelia.ev:id/txt_hvac_temp")
                    ok = (hvac_node is not None and "21.0" in hvac_node.text) or (step.property_reads.get("HVAC_TEMPERATURE_SET") == 21.0)
                    uris = [step.screenshot_uri] if step.screenshot_uri else []
                    return ok, f"hvac_ui={hvac_node.text if hvac_node else 'N/A'}, vhal={step.property_reads.get('HVAC_TEMPERATURE_SET')}", step.timing_ms, uris

                run.results.append(self._run_with_flaky_quarantine(
                    run_id, "remote_climate_hvac_sync", "functional", "SC-04", check_sc04
                ))

            # ---------------------------------------------------------------
            # Suite 5: Localisation Check (VAR-C de-DE)
            # ---------------------------------------------------------------
            if variant_id == "VAR-C":
                def check_loc() -> Tuple[bool, str, Optional[float], List[str]]:
                    consent = t_home.ui_nodes.get("com.aurelia.ev:id/banner_eu_consent")
                    ok = consent is not None
                    uris = [t_home.screenshot_uri] if t_home.screenshot_uri else []
                    return ok, f"eu_consent_banner={'visible' if ok else 'missing'}", 0.0, uris

                run.results.append(self._run_with_flaky_quarantine(
                    run_id, "eu_localisation_and_consent_prompt", "localisation", "SC-02", check_loc
                ))

            run.status = "COMPLETED"
        except Exception as exc:
            logger.error("[%s] Run failed with exception: %s", run_id, exc, exc_info=True)
            run.status = "ERROR"
            run.results.append(TestResult(
                result_id=f"res-{uuid.uuid4().hex[:8]}",
                run_id=run_id,
                test_id="runner_execution",
                suite="functional",
                scenario_id="ALL",
                status=TestStatus.FAIL,
                message=str(exc),
            ))

        wall_s = round(time.perf_counter() - t0, 2)
        run.ended_at = datetime.utcnow().isoformat() + "Z"
        run.wall_time_seconds = wall_s
        run.compute_minutes = round(wall_s / 60.0, 3)
        run.cost_usd = round(run.compute_minutes * 0.015, 4)

        # Persist trace bundle JSON & JUnit XML
        trace_path = os.path.join(run_dir, "trace_bundle.json")
        junit_path = os.path.join(run_dir, "junit.xml")
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(run.model_dump(), f, indent=2)
        _write_junit_xml(run, junit_path)
        run.trace_json_path = trace_path
        run.junit_xml_path = junit_path

        logger.info("[%s] Completed in %.1fs (%d/%d passed)",
                    run_id, wall_s, sum(1 for r in run.results if r.status == TestStatus.PASS), len(run.results))
        return run

    def run_release_across_variants(
        self,
        release_id: str,
        target_variants: Optional[List[str]] = None,
        scenarios: Optional[List[str]] = None,
    ) -> List[RunRecord]:
        """Runs all selected scenarios in parallel across all ONLINE target variants (M5-FR1)."""
        from fleet.manager import _instances, _lock as fleet_lock
        from fleet.models import InstanceStatus

        sc_list = scenarios or ["SC-01", "SC-02", "SC-03", "SC-04"]

        with fleet_lock:
            online = [i for i in _instances.values() if i.status == InstanceStatus.ONLINE and i.adb_serial]

        if target_variants:
            wanted = set(target_variants)
            online = [i for i in online if i.variant_id in wanted]

        if not online:
            raise ValueError("No ONLINE AAOS cockpit instances available for test execution. Launch VAR-A/B/C first.")

        # One instance per variant
        by_variant: Dict[str, object] = {}
        for inst in online:
            if inst.variant_id not in by_variant:
                by_variant[inst.variant_id] = inst

        records: List[RunRecord] = []
        with ThreadPoolExecutor(max_workers=len(by_variant)) as pool:
            futures = [
                pool.submit(
                    self.execute_variant_run,
                    release_id,
                    vid,
                    inst.instance_id,
                    inst.adb_serial,
                    sc_list,
                )
                for vid, inst in by_variant.items()
            ]
            for fut in futures:
                records.append(fut.result())

        return records

    def latest_runs_by_variant(self, release_id: str) -> Dict[str, RunRecord]:
        """Returns the most recent completed RunRecord per variant for a given release_id."""
        latest: Dict[str, RunRecord] = {}
        for r in self.runs.values():
            if r.release_id == release_id:
                prev = latest.get(r.variant_id)
                if prev is None or r.started_at >= prev.started_at:
                    latest[r.variant_id] = r
        return latest


# Singleton runner instance
scenario_runner = ScenarioRunner()
