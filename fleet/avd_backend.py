"""
AVD Backend — launches and manages Android Virtual Devices (local phase).
Cloud phase: swap this module for a Cuttlefish backend; API stays identical.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger("fleet.avd")

# Base ADB port for emulator allocation (5554, 5556, 5558 ...)
_BASE_ADB_PORT = 5554
_PORT_STEP = 2

# Track allocated ports to avoid collisions
_allocated_ports: set[int] = set()


def _find_sdk_root() -> str:
    candidates = [
        os.environ.get("ANDROID_HOME", ""),
        os.environ.get("ANDROID_SDK_ROOT", ""),
        os.path.expanduser("~\\AppData\\Local\\Android\\Sdk"),
        os.path.expanduser("~/AppData/Local/Android/Sdk"),
        # Windows: common hardcoded paths
        r"C:\Users\JatinChhabra\AppData\Local\Android\Sdk",
        r"C:\Users\brave\AppData\Local\Android\Sdk",
        r"C:\Android\Sdk",
        "/opt/android/sdk",
    ]
    for path in candidates:
        if not path:
            continue
        try:
            if os.path.isfile(os.path.join(path, "emulator", "emulator.exe")) or \
               os.path.isfile(os.path.join(path, "platform-tools", "adb.exe")):
                return path
        except Exception:
            pass
    
    # Sensible default on Windows
    if os.name == "nt":
        return r"C:\Users\JatinChhabra\AppData\Local\Android\Sdk"
        
    raise RuntimeError(
        "Android SDK not found. Set ANDROID_HOME or ANDROID_SDK_ROOT "
        "or run docs/spikes/scripts/set_android_env.ps1"
    )


# Lazily resolved — allows import without SDK present (e.g., unit tests)
_SDK_ROOT: str = ""


def _get_sdk_root() -> str:
    global _SDK_ROOT
    if not _SDK_ROOT:
        _SDK_ROOT = _find_sdk_root()
    return _SDK_ROOT


@property  # type: ignore[misc]
def SDK_ROOT() -> str:  # noqa: N802
    return _get_sdk_root()
def _emulator_path() -> str:
    root = _get_sdk_root()
    return os.path.join(root, "emulator", "emulator.exe" if os.name == "nt" else "emulator")


def _adb_path() -> str:
    root = _get_sdk_root()
    return os.path.join(root, "platform-tools", "adb.exe" if os.name == "nt" else "adb")


def _next_available_port() -> int:
    port = _BASE_ADB_PORT
    while port in _allocated_ports:
        port += _PORT_STEP
    _allocated_ports.add(port)
    return port


def _run_adb(args: list[str], serial: Optional[str] = None, check: bool = False) -> subprocess.CompletedProcess:
    cmd = [_adb_path()]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _wait_for_online(serial: str, timeout: int = 300) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _run_adb(["devices"])
        if re.search(rf"{serial}\s+device", result.stdout):
            return True
        time.sleep(3)
    return False


def _wait_for_boot(serial: str, timeout: int = 180) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _run_adb(["shell", "getprop", "sys.boot_completed"], serial=serial)
        if result.stdout.strip() == "1":
            return True
        time.sleep(4)
    return False


def _apply_locale(serial: str, locale: str):
    """Override locale via system props (best-effort on emulator builds)."""
    _run_adb(["root"], serial=serial)
    _run_adb(["shell", "setprop", "persist.sys.locale", locale], serial=serial)
    _run_adb(["shell", "setprop", "debug.cora.locale", locale], serial=serial)
    _run_adb(["shell", "settings", "put", "system", "system_locales", locale], serial=serial)
    # Restart locale-dependent services
    _run_adb(["shell", "am", "broadcast", "-a", "android.intent.action.LOCALE_CHANGED"], serial=serial)
    logger.info("Applied locale %s to %s", locale, serial)


def _apply_feature_flags(serial: str, flags: dict):
    """Inject feature flags as system properties for the demo apps to read."""
    for key, value in flags.items():
        _run_adb(["shell", "setprop", f"debug.cora.{key.lower()}", str(value)], serial=serial)
    logger.info("Applied feature flags %s to %s", flags, serial)


def _apply_display(serial: str, display: Optional[dict] = None):
    """Ensure display resolution & density match variant specifications."""
    if not display:
        return
    w = display.get("width")
    h = display.get("height")
    density = display.get("density")
    if w and h:
        _run_adb(["shell", "wm", "size", f"{w}x{h}"], serial=serial)
    if density:
        _run_adb(["shell", "wm", "density", str(density)], serial=serial)
    logger.info("Applied display config %s to %s", display, serial)


def launch_avd(
    avd_name: str,
    adb_port: int,
    locale: str = "en-US",
    feature_flags: Optional[dict] = None,
    display: Optional[dict] = None,
) -> Tuple[int, str, float]:
    """
    Launches the named AVD on `adb_port` (or adopts it if already running).
    Returns (pid, serial, boot_seconds).
    """
    serial = f"emulator-{adb_port}"
    _allocated_ports.add(adb_port)

    t0 = time.time()

    # Check if instance is already running
    devices_check = _run_adb(["devices"])
    if re.search(rf"{serial}\s+device", devices_check.stdout):
        logger.info("AVD %s is already running on %s — adopting active instance.", avd_name, serial)
        _wait_for_boot(serial, timeout=30)
        boot_seconds = round(time.time() - t0, 1)
        _apply_locale(serial, locale)
        if feature_flags:
            _apply_feature_flags(serial, feature_flags)
        if display:
            _apply_display(serial, display)
        return 0, serial, boot_seconds

    logger.info("Launching AVD %s on port %d (serial: %s)...", avd_name, adb_port, serial)
    proc = subprocess.Popen(
        [
            _emulator_path(),
            "-avd", avd_name,
            "-port", str(adb_port),
            "-no-snapshot-load",
            "-no-audio",
            "-no-boot-anim",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not _wait_for_online(serial, timeout=120):
        proc.terminate()
        raise RuntimeError(f"Emulator {serial} did not come online within 120s")

    if not _wait_for_boot(serial, timeout=180):
        proc.terminate()
        raise RuntimeError(f"Emulator {serial} did not complete boot within 180s")

    boot_seconds = round(time.time() - t0, 1)
    logger.info("AVD %s online in %.1f s (serial: %s)", avd_name, boot_seconds, serial)

    # Apply locale, feature flags & display overrides
    _apply_locale(serial, locale)
    if feature_flags:
        _apply_feature_flags(serial, feature_flags)
    if display:
        _apply_display(serial, display)

    return proc.pid, serial, boot_seconds


def stop_avd(serial: str, pid: Optional[int] = None):
    """Sends emu kill to gracefully shut down the given emulator serial."""
    if pid == 0:
        logger.info("Instance was adopted (pid=0); releasing without killing emulator %s.", serial)
        try:
            port = int(serial.split("-")[-1])
            _allocated_ports.discard(port)
        except ValueError:
            pass
        return

    logger.info("Stopping emulator %s (pid=%s)...", serial, pid)
    _run_adb(["emu", "kill"], serial=serial)
    # Extract port from serial and free it
    try:
        port = int(serial.split("-")[-1])
        _allocated_ports.discard(port)
    except ValueError:
        pass


def is_device_alive(serial: str) -> bool:
    """Checks if an emulator serial is currently listed as 'device' in adb devices."""
    if not serial:
        return False
    try:
        res = _run_adb(["devices"])
        return bool(re.search(rf"^{re.escape(serial)}\s+device\b", res.stdout, re.MULTILINE))
    except Exception:
        return False


def _get_installed_version(serial: str, package_name: str) -> Optional[str]:
    """Returns installed versionName of package_name on device, or None if not installed."""
    try:
        res = _run_adb(["shell", "dumpsys", "package", package_name], serial=serial)
        m = re.search(r"versionName=([^\s]+)", res.stdout)
        return m.group(1).strip() if m else None
    except Exception:
        return None


def ensure_demo_apps(serial: str, build_tag: str = "v1.0") -> dict[str, str]:
    """
    Smart conditional installer for M3 Demo OEM Apps:
      - Checks if APP-2 (com.aurelia.rearview) and APP-1 (com.aurelia.ev) are already installed
        at the requested build_tag version. Only runs `adb install` if missing or version differs,
        keeping normal boot times fast.
      - Launches APP-1 (com.aurelia.ev/.MainActivity) so the cockpit opens directly into Aurelia EV.
    """
    build_map = {
        "v1.0": ("aurelia-ev-v1.0.apk", "1.0.0"),
        "v1.1": ("aurelia-ev-v1.1.apk", "1.1.0"),
        "v1.1-fix": ("aurelia-ev-v1.1-fix.apk", "1.1.1-fix"),
    }
    ev_apk_name, expected_ev_ver = build_map.get(build_tag, ("aurelia-ev-v1.0.apk", "1.0.0"))
    dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "dist"))
    status_info: dict[str, str] = {}

    # 1. APP-2 Rear-view stand-in (install only if missing)
    rv_apk = os.path.join(dist_dir, "aurelia-rearview-v1.0.apk")
    rv_ver = _get_installed_version(serial, "com.aurelia.rearview")
    if not rv_ver and os.path.isfile(rv_apk):
        logger.info("[%s] Installing APP-2 Rear-view (not yet installed)...", serial)
        _run_adb(["install", "-r", "-d", "-g", rv_apk], serial=serial)
        rv_ver = _get_installed_version(serial, "com.aurelia.rearview") or "1.0.0"
    status_info["com.aurelia.rearview"] = rv_ver or "missing"

    # 2. APP-1 Aurelia EV (install only if missing or version mismatch)
    ev_apk = os.path.join(dist_dir, ev_apk_name)
    ev_ver = _get_installed_version(serial, "com.aurelia.ev")
    if ev_ver != expected_ev_ver and os.path.isfile(ev_apk):
        logger.info("[%s] Installing APP-1 Aurelia EV %s (current=%s -> target=%s)...",
                    serial, build_tag, ev_ver, expected_ev_ver)
        _run_adb(["install", "-r", "-d", "-g", ev_apk], serial=serial)
        ev_ver = _get_installed_version(serial, "com.aurelia.ev") or expected_ev_ver
    else:
        logger.info("[%s] APP-1 Aurelia EV %s already installed; skipping install.", serial, ev_ver)
    status_info["com.aurelia.ev"] = ev_ver or "missing"

    # 3. Auto-launch Aurelia EV dashboard on cockpit screen
    if ev_ver:
        _run_adb(["shell", "am", "start", "-n", "com.aurelia.ev/.MainActivity"], serial=serial)

    return status_info


def read_properties(serial: str, prop_names: list[str]) -> dict[str, str]:
    """Reads one or more system properties from the running emulator."""
    results = {}
    for prop in prop_names:
        res = _run_adb(["shell", "getprop", prop], serial=serial)
        results[prop] = res.stdout.strip()
    return results


def next_port() -> int:
    return _next_available_port()
