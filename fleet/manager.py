"""
Fleet Manager Service — FastAPI
Implements /v1/fleet/instances endpoints as defined in the POC Build Spec §6.

Run locally:
    cd cockpit-ota
    python -m uvicorn fleet.manager:app --reload --port 8001
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware

from fleet.models import (
    FleetInstance,
    InstanceStatus,
    LaunchRequest,
    LaunchResponse,
    InstanceListResponse,
    VariantConfig,
)
import fleet.avd_backend as avd
from fleet.stream import get_stream_url, start_stream, stop_stream, capture_screenshot
from signals.router import router as scenarios_router
from apps.companion.router import router as companion_cloud_router
from ota.router import router as ota_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("fleet.manager")

# ---------------------------------------------------------------------------
# App & state
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CORA Fleet Manager",
    description="Virtual AAOS Cockpit Fleet — Cockpit & OTA Release Assurance POC",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in cloud phase via IAP
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scenarios_router)
app.include_router(companion_cloud_router)
app.include_router(ota_router)

# In-memory instance registry (replace with DB in M7 integration)
_instances: Dict[str, FleetInstance] = {}
_stream_procs: Dict[str, object] = {}  # instance_id -> Popen
_injectors: Dict[str, object] = {}     # adb_serial -> VhalInjector (persistent shell cache)
_lock = threading.Lock()


def _get_injector(serial: str):
    """Returns a cached VhalInjector with a warm persistent ADB shell for the given serial."""
    with _lock:
        inj = _injectors.get(serial)
        if inj is None:
            import sys, pathlib
            root_dir = str(pathlib.Path(__file__).parent.parent)
            if root_dir not in sys.path:
                sys.path.insert(0, root_dir)
            from signals.injector import VhalInjector
            sdk_root = avd._get_sdk_root()
            adb_path = os.path.join(sdk_root, "platform-tools", "adb.exe" if os.name == "nt" else "adb")
            inj = VhalInjector(adb_path=adb_path, serial=serial)
            _injectors[serial] = inj
        return inj


def _release_injector(serial: Optional[str]):
    if not serial:
        return
    with _lock:
        inj = _injectors.pop(serial, None)
    if inj is not None:
        try:
            inj.close()
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Variant config loader
# ---------------------------------------------------------------------------
_VARIANTS_FILE = os.path.join(os.path.dirname(__file__), "variants.yaml")

def _load_variants() -> Dict[str, VariantConfig]:
    with open(_VARIANTS_FILE, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return {k: VariantConfig(**v) for k, v in raw["variants"].items()}

VARIANTS: Dict[str, VariantConfig] = _load_variants()

# ---------------------------------------------------------------------------
# VIN-like ID generator (fictional, non-real WMI per spec §4 M1-FR5)
# ---------------------------------------------------------------------------
def _make_vin(variant_id: str, seq: int) -> str:
    # Format: ZFA (fictional Ferfier WMI) + 6-char variant code + 5-digit seq
    variant_code = variant_id.replace("-", "").upper().ljust(6, "0")[:6]
    return f"ZFA{variant_code}{seq:05d}"

_vin_counter: Dict[str, int] = {}

def _next_vin(variant_id: str) -> str:
    _vin_counter[variant_id] = _vin_counter.get(variant_id, 0) + 1
    return _make_vin(variant_id, _vin_counter[variant_id])

# ---------------------------------------------------------------------------
# Background launcher (runs boot in a thread so API returns immediately)
# ---------------------------------------------------------------------------
def _boot_instance(inst: FleetInstance, variant: VariantConfig):
    try:
        with _lock:
            inst.status = InstanceStatus.STARTING

        pid, serial, boot_secs = avd.launch_avd(
            avd_name=variant.avd_name,
            adb_port=inst.adb_port,
            locale=variant.locale,
            feature_flags=variant.feature_flags,
            display=variant.display if variant.display else None,
        )

        # Read back key properties for validation
        props = avd.read_properties(serial, [
            "ro.product.locale",
            "ro.build.characteristics",
            "ro.build.version.sdk",
        ])

        # Smart conditional install & auto-launch of APP-1 (Aurelia EV) + APP-2 (Rear-view)
        try:
            app_versions = avd.ensure_demo_apps(serial, inst.build_tag)
            props["app.aurelia.ev"] = app_versions.get("com.aurelia.ev", "unknown")
            props["app.aurelia.rearview"] = app_versions.get("com.aurelia.rearview", "unknown")
        except Exception as app_exc:
            logger.warning("[%s] Auto-install/launch of demo apps skipped: %s", serial, app_exc)

        # Start screen stream
        stream_proc = start_stream(serial, inst.instance_id, window_title=f"CORA | {inst.variant_id} | {inst.build_tag}")
        stream_url = get_stream_url(inst.instance_id, serial, inst.adb_port)

        with _lock:
            inst.pid = pid
            inst.adb_serial = serial
            inst.boot_time_seconds = boot_secs
            inst.stream_url = stream_url
            inst.properties = props
            inst.status = InstanceStatus.ONLINE
            _stream_procs[inst.instance_id] = stream_proc

        logger.info(
            "[ONLINE] %s (%s) booted in %.1fs — serial=%s",
            inst.instance_id, inst.variant_id, boot_secs, serial
        )

    except Exception as exc:
        with _lock:
            inst.status = InstanceStatus.ERROR
            inst.properties["error"] = str(exc)
        logger.error("Failed to boot %s: %s", inst.instance_id, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "fleet-manager", "timestamp": datetime.utcnow().isoformat()}


@app.get("/v1/fleet/variants")
def list_variants():
    """List available variant configs."""
    return {"variants": {k: v.model_dump() for k, v in VARIANTS.items()}}


@app.post("/v1/fleet/instances", response_model=LaunchResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_instances(request: LaunchRequest, background_tasks: BackgroundTasks):
    """
    Launch one or more AAOS cockpit instances for a given variant and build tag.
    Boot is asynchronous — poll GET /v1/fleet/instances/{id} for ONLINE status.
    Implements M1-FR1, M1-FR2, M1-FR3, M1-FR4, M1-FR5.
    """
    if request.variant_id not in VARIANTS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown variant '{request.variant_id}'. Valid variants: {list(VARIANTS.keys())}"
        )

    variant = VARIANTS[request.variant_id]
    launched: List[FleetInstance] = []

    for _ in range(request.count):
        adb_port = avd.next_port()
        instance_id = f"inst-{request.variant_id.lower().replace('-', '')}-{uuid.uuid4().hex[:6]}"
        vin = _next_vin(request.variant_id)

        inst = FleetInstance(
            instance_id=instance_id,
            variant_id=request.variant_id,
            vin_like=vin,
            build_tag=request.build_tag,
            adb_port=adb_port,
            status=InstanceStatus.STARTING,
        )

        with _lock:
            _instances[instance_id] = inst

        # Boot runs in background thread; API returns STARTING immediately
        background_tasks.add_task(_boot_instance, inst, variant)
        launched.append(inst)
        logger.info("Queued boot: %s variant=%s build=%s port=%d vin=%s",
                    instance_id, request.variant_id, request.build_tag, adb_port, vin)

    return LaunchResponse(instances=launched)


@app.get("/v1/fleet/instances", response_model=InstanceListResponse)
def list_instances(variant_id: Optional[str] = None, status: Optional[str] = None):
    """
    List all fleet instances. Optional filters: ?variant_id=VAR-A, ?status=ONLINE
    Reconciles live status with ADB so manually closed or crashed emulators are marked STOPPED.
    """
    with _lock:
        for inst in _instances.values():
            if inst.status == InstanceStatus.ONLINE and inst.adb_serial:
                if not avd.is_device_alive(inst.adb_serial):
                    logger.info("Instance %s (%s) is no longer alive in adb; marking STOPPED", inst.instance_id, inst.adb_serial)
                    inst.status = InstanceStatus.STOPPED
                    stream_proc = _stream_procs.pop(inst.instance_id, None)
                    stop_stream(stream_proc)

        instances = list(_instances.values())

    if status:
        instances = [i for i in instances if i.status.value == status.upper()]
    else:
        # By default exclude STOPPED instances from the active list
        instances = [i for i in instances if i.status != InstanceStatus.STOPPED]

    if variant_id:
        instances = [i for i in instances if i.variant_id == variant_id]

    return InstanceListResponse(instances=instances, total=len(instances))


@app.get("/v1/fleet/instances/{instance_id}", response_model=FleetInstance)
def get_instance(instance_id: str):
    """Get a single fleet instance by ID. Poll this for ONLINE status after launch."""
    with _lock:
        inst = _instances.get(instance_id)
        if inst and inst.status == InstanceStatus.ONLINE and inst.adb_serial:
            if not avd.is_device_alive(inst.adb_serial):
                logger.info("Instance %s (%s) is no longer alive in adb; marking STOPPED", inst.instance_id, inst.adb_serial)
                inst.status = InstanceStatus.STOPPED
                stream_proc = _stream_procs.pop(inst.instance_id, None)
                stop_stream(stream_proc)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_id}' not found")
    return inst


@app.delete("/v1/fleet/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def stop_instance(instance_id: str):
    """
    Stop and tear down a running cockpit instance. Implements M1-FR6.
    Clean re-create within 5 minutes target.
    """
    with _lock:
        inst = _instances.get(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_id}' not found")

    inst.status = InstanceStatus.STOPPING

    if inst.adb_serial:
        _release_injector(inst.adb_serial)
        try:
            avd.stop_avd(inst.adb_serial, inst.pid)
        except Exception as exc:
            logger.warning("Error stopping emulator %s: %s", inst.adb_serial, exc)

    stream_proc = _stream_procs.pop(instance_id, None)
    stop_stream(stream_proc)

    with _lock:
        inst.status = InstanceStatus.STOPPED

    logger.info("Stopped instance %s (%s)", instance_id, inst.variant_id)


@app.post("/v1/fleet/instances/{instance_id}/screenshot")
def take_screenshot(instance_id: str):
    """
    Takes a screenshot of the running instance. Used by M5 test runner for trace evidence.
    Returns the file path of the saved screenshot.
    """
    with _lock:
        inst = _instances.get(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_id}' not found")
    if inst.status != InstanceStatus.ONLINE or not inst.adb_serial:
        raise HTTPException(status_code=409, detail=f"Instance '{instance_id}' is not ONLINE")

    screenshots_dir = os.path.join(os.path.dirname(__file__), "..", "evidence", "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    filename = f"{instance_id}_{int(datetime.utcnow().timestamp())}.png"
    output_path = os.path.join(screenshots_dir, filename)

    success = capture_screenshot(inst.adb_serial, output_path)
    if not success:
        raise HTTPException(status_code=500, detail="Screenshot capture failed")

    return {"path": output_path, "filename": filename, "instance_id": instance_id}


@app.post("/v1/fleet/instances/{instance_id}/signals")
def inject_signal(instance_id: str, body: dict):
    """
    Debug endpoint: inject a single VHAL property into a running instance.
    Body: {"vss_path": "Vehicle.Powertrain.Transmission.SelectedGear", "value": "GEAR_REVERSE"}
    Implements spec §6 POST /v1/fleet/instances/{id}/signals
    """
    with _lock:
        inst = _instances.get(instance_id)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_id}' not found")
    if inst.status != InstanceStatus.ONLINE or not inst.adb_serial:
        raise HTTPException(status_code=409, detail=f"Instance '{instance_id}' is not ONLINE")

    injector = _get_injector(inst.adb_serial)

    try:
        result = injector.inject_vss(body["vss_path"], body["value"])
        logger.info(
            "[SIGNAL] %s (%s) %s -> %s (%s) in %.1fms | adb_out=%r",
            instance_id,
            inst.adb_serial,
            result["vss_path"],
            result["injected_value"],
            result["vhal_property_name"],
            result["latency_ms"],
            result.get("response", ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing field: {exc}")
    except Exception as exc:
        logger.error("[SIGNAL ERROR] %s: %s", instance_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))

    return result
