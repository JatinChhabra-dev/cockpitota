"""
Real Live ADB Trace Recorder for Module 5 (Spec §4 M5, §8.2).
Captures genuine AAOS device evidence per scenario step:
  - UI hierarchy XML (`uiautomator dump`) -> resource IDs, text, enabled, focused, bounds, SHA-256 ui_hash
  - Top-window z-order (`dumpsys activity activities`)
  - VHAL property read-backs (`cmd car_service get-property-value`)
  - Real PNG screenshots (`adb exec-out screencap -p`)
  - Real logcat window (`AureliaEV`, `AureliaRearView`)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fleet.avd_backend import _adb_path
from engine.models import TraceStep, UiNode


def _adb_text(serial: str, args: List[str], timeout: float = 15.0) -> Tuple[int, str]:
    cmd = [_adb_path(), "-s", serial] + args
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return res.returncode, (res.stdout or "").strip()


def capture_top_activity(serial: str) -> str:
    """Returns the top resumed Activity component name from Android ActivityManager."""
    rc, out = _adb_text(serial, ["shell", "dumpsys", "activity", "activities"], timeout=10.0)
    if rc != 0:
        return ""
    for line in out.splitlines():
        if "topResumedActivity=" in line or "mResumedActivity:" in line or "ResumedActivity:" in line:
            m = re.search(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)", line)
            if m:
                return m.group(1)
            return line.strip()
    return ""


def capture_ui_tree(serial: str) -> Tuple[Dict[str, UiNode], str]:
    """
    Runs real `uiautomator dump` on the AAOS device and extracts all Aurelia app UI nodes
    (resource-id, text, enabled, focused, bounds) plus a deterministic SHA-256 ui_hash.
    """
    dump_path = "/sdcard/cora_window_dump.xml"
    _adb_text(serial, ["shell", "uiautomator", "dump", dump_path], timeout=12.0)
    rc, xml_text = _adb_text(serial, ["shell", "cat", dump_path], timeout=8.0)

    nodes: Dict[str, UiNode] = {}
    if rc == 0 and "<hierarchy" in xml_text:
        try:
            xml_start = xml_text.index("<hierarchy")
            root = ET.fromstring(xml_text[xml_start:])
            for elem in root.iter("node"):
                rid = (elem.attrib.get("resource-id") or "").strip()
                if not rid:
                    continue
                # Keep all Aurelia app nodes (exclude unrelated Android system clock/status bar churn)
                if not (rid.startswith("com.aurelia.") or rid.startswith("android:id/alertTitle")):
                    continue
                nodes[rid] = UiNode(
                    resource_id=rid,
                    text=(elem.attrib.get("text") or "").strip(),
                    enabled=(elem.attrib.get("enabled", "true").lower() == "true"),
                    focused=(elem.attrib.get("focused", "false").lower() == "true"),
                    bounds=(elem.attrib.get("bounds") or "").strip(),
                )
        except Exception:
            pass

    # Deterministic hash over sorted resource IDs + text + enabled state
    canonical = json.dumps(
        {k: {"text": v.text, "enabled": v.enabled} for k, v in sorted(nodes.items())},
        sort_keys=True,
    )
    ui_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return nodes, ui_hash


def capture_vhal_properties(serial: str) -> Dict[str, Any]:
    """Reads live VHAL property values back from Android CarService."""
    props = {
        "PERF_VEHICLE_SPEED": (291504647, 0, "float"),
        "GEAR_SELECTION": (289408000, 0, "int"),
        "EV_BATTERY_LEVEL": (291504905, 0, "float"),
        "EV_CHARGE_PORT_OPEN": (287310602, 0, "int"),
        "EV_CHARGE_PORT_CONNECTED": (287310603, 0, "int"),
        "HVAC_TEMPERATURE_SET": (358614275, 49, "float"),
    }
    reads: Dict[str, Any] = {}
    for name, (prop_id, area_id, dtype) in props.items():
        rc, out = _adb_text(serial, ["shell", "cmd", "car_service", "get-property-value", str(prop_id), str(area_id)], timeout=4.0)
        if rc == 0:
            m = re.search(r"value=([0-9.\-]+|true|false)", out, re.IGNORECASE)
            if m:
                raw = m.group(1)
                if dtype == "float":
                    try:
                        reads[name] = round(float(raw), 2)
                    except ValueError:
                        reads[name] = raw
                elif dtype == "int":
                    if raw.lower() == "true":
                        reads[name] = 1
                    elif raw.lower() == "false":
                        reads[name] = 0
                    else:
                        try:
                            reads[name] = int(float(raw))
                        except ValueError:
                            reads[name] = raw
    return reads


def capture_screenshot(serial: str, out_path: str) -> Optional[str]:
    """Captures a genuine PNG screenshot from the AAOS emulator."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cmd = [_adb_path(), "-s", serial, "exec-out", "screencap", "-p"]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=15.0, check=False)
        if res.returncode == 0 and res.stdout and res.stdout.startswith(b"\x89PNG"):
            with open(out_path, "wb") as f:
                f.write(res.stdout)
            return out_path
    except Exception:
        pass
    return None


def capture_logcat_window(serial: str, max_lines: int = 30) -> List[str]:
    """Captures recent AureliaEV / AureliaRearView logcat lines."""
    rc, out = _adb_text(serial, ["logcat", "-d", "-s", "AureliaEV:I", "AureliaEV:E", "AureliaRearView:I"], timeout=8.0)
    if rc != 0 or not out:
        return []
    lines = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.startswith("---------")]
    return lines[-max_lines:]


def clear_logcat(serial: str):
    _adb_text(serial, ["logcat", "-c"], timeout=5.0)


def record_trace_step(
    run_id: str,
    scenario_id: str,
    scenario_step: str,
    variant_id: str,
    serial: str,
    run_dir: str,
    timing_ms: Optional[float] = None,
    safety_relevant: bool = False,
) -> TraceStep:
    """Captures a complete real-device TraceStep (UI tree, z-order, VHAL, screenshot, logcat)."""
    top_act = capture_top_activity(serial)
    ui_nodes, ui_hash = capture_ui_tree(serial)
    vhal_reads = capture_vhal_properties(serial)
    safe_step = re.sub(r"[^a-zA-Z0-9_\-]", "_", f"{scenario_id}_{scenario_step}")
    shot_path = capture_screenshot(serial, os.path.join(run_dir, f"{safe_step}.png"))
    logs = capture_logcat_window(serial)

    return TraceStep(
        run_id=run_id,
        scenario_id=scenario_id,
        scenario_step=scenario_step,
        variant_id=variant_id,
        top_activity=top_act,
        ui_hash=ui_hash,
        ui_nodes=ui_nodes,
        property_reads=vhal_reads,
        timing_ms=timing_ms,
        screenshot_uri=shot_path,
        logcat_excerpt=logs,
        safety_relevant=safety_relevant,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
