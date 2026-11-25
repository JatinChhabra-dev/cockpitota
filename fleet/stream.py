"""
Screen Streaming Module
Local phase: uses scrcpy (if installed) or returns an adb-shell-based fallback.
Cloud phase: replace with WebRTC per-instance stream URL from Cuttlefish.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger("fleet.stream")

_scrcpy_checked: Optional[bool] = None


def _is_scrcpy_available() -> bool:
    global _scrcpy_checked
    if _scrcpy_checked is not None:
        return _scrcpy_checked
    try:
        result = subprocess.run(["scrcpy", "--version"], capture_output=True, text=True)
        _scrcpy_checked = (result.returncode == 0)
    except Exception:
        _scrcpy_checked = False
    return _scrcpy_checked


def get_stream_url(instance_id: str, serial: str, adb_port: int) -> Optional[str]:
    """
    Returns the stream URL/descriptor for a live cockpit instance.

    Local phase: scrcpy launched as sidecar — returns a local display identifier.
    Cloud phase: returns WebRTC URL from Cuttlefish stream proxy.
    """
    if _is_scrcpy_available():
        return f"scrcpy://local/{serial}?title={instance_id}"
    else:
        # Fallback: ADB screencap endpoint (for static screenshots in console)
        return f"adb://screencap/{serial}"


def start_stream(serial: str, instance_id: str, window_title: Optional[str] = None) -> Optional[subprocess.Popen]:
    """
    Launches a scrcpy window for the given emulator serial.
    Returns the Popen process so the fleet manager can track and kill it.
    Non-blocking: runs in background.
    """
    if not _is_scrcpy_available():
        logger.warning("scrcpy not found — skipping stream window for %s. Install via: winget install Genymobile.scrcpy", serial)
        return None

    title = window_title or instance_id
    cmd = [
        "scrcpy",
        "--serial", serial,
        "--window-title", title,
        "--always-on-top",
        "--stay-awake",
    ]
    logger.info("Starting scrcpy stream for %s: %s", serial, " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc
    except Exception as exc:
        logger.error("Failed to start scrcpy for %s: %s", serial, exc)
        return None


def stop_stream(stream_proc: Optional[subprocess.Popen]):
    """Terminates a scrcpy stream process."""
    if stream_proc and stream_proc.poll() is None:
        stream_proc.terminate()


def capture_screenshot(serial: str, output_path: str) -> bool:
    """
    Takes a screenshot of the running emulator via adb screencap.
    Returns True on success. Used by M5 test runner for trace evidence.
    """
    from fleet.avd_backend import _adb_path

    adb_bin = _adb_path()
    result = subprocess.run(
        [adb_bin, "-s", serial, "shell", "screencap", "-p", "/sdcard/screencap_tmp.png"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error("screencap failed for %s: %s", serial, result.stderr)
        return False

    pull = subprocess.run(
        [adb_bin, "-s", serial, "pull", "/sdcard/screencap_tmp.png", output_path],
        capture_output=True, text=True
    )
    if pull.returncode != 0:
        logger.error("adb pull failed for %s: %s", serial, pull.stderr)
        return False

    logger.info("Screenshot saved: %s", output_path)
    return True
