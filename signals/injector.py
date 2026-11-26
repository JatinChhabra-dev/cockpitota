"""
Vehicle Signal Injector for AAOS
Implements VSS -> VHAL translation and serialized adb car_service event injection.
"""

import os
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, Optional, Union
import yaml


class VhalInjector:
    def __init__(self, adb_path: str = "adb", serial: Optional[str] = None, map_file: Optional[str] = None):
        # Auto-resolve ADB path if default was given and not on PATH
        if adb_path == "adb" and not shutil.which("adb"):
            try:
                from fleet.avd_backend import _adb_path
                adb_path = _adb_path()
            except Exception:
                pass
        self.adb_path = adb_path
        self.serial = serial

        # Load mapping file once per injector instance
        if not map_file:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            map_file = os.path.join(base_dir, "vss_vhal_map.yaml")

        with open(map_file, "r", encoding="utf-8") as f:
            self.spec = yaml.safe_load(f)

        self.mappings = self.spec.get("mappings", {})
        self.battery_capacity_kwh = self.spec.get("battery_capacity_kwh", 75.0)

        # Serialize injections per device so concurrent requests execute in strict order
        self._lock = threading.Lock()

    def close(self):
        """No-op cleanup hook for cached injector lifecycle."""
        pass

    def _exec_adb(self, cmd_args: list[str], timeout: float = 5.0) -> str:
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(cmd_args)

        with self._lock:
            try:
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"ADB command timed out after {timeout}s: {' '.join(cmd_args)}") from exc

        if res.returncode != 0:
            raise RuntimeError(f"ADB execution failed: {res.stderr.strip() or res.stdout.strip()}")
        return res.stdout.strip()

    def inject_vhal_raw(
        self,
        prop_id: int,
        value: Union[int, float, str],
        area_id: int = 0,
        data_type: str = "int",
    ) -> str:
        """
        Writes a property directly into AIDL FakeVehicleHardware via:
          adb shell dumpsys android.hardware.automotive.vehicle.IVehicle/default --set <prop> [-a <area>] -f|-i <val>
        Writing directly to FakeVehicleHardware persists the value across continuous 1Hz VHAL refreshes
        (so speed/SoC never snap back to 0). Falls back to `cmd car_service inject-vhal-event` if unavailable.
        """
        val_flag = "-f" if data_type == "float" else "-i"
        vhal_args = [
            "shell", "dumpsys",
            "android.hardware.automotive.vehicle.IVehicle/default",
            "--set", str(prop_id),
        ]
        if area_id != 0:
            vhal_args.extend(["-a", str(area_id)])
        vhal_args.extend([val_flag, str(value)])

        try:
            out = self._exec_adb(vhal_args)
            if "Set property:" in out:
                return out
            # If AIDL VHAL service rejected or wasn't found, fall back below
            if "Can't find service" not in out and "Failed" not in out and "Error" not in out and "invalid" not in out.lower():
                return out
        except Exception:
            pass

        # Fallback: cmd car_service inject-vhal-event
        args = ["shell", "cmd", "car_service", "inject-vhal-event", str(prop_id)]
        if area_id != 0:
            args.extend(["-z", str(area_id)])
        args.append(str(value))
        return self._exec_adb(args)

    def inject_vss(self, vss_path: str, value: Any, area_id: Optional[int] = None) -> Dict[str, Any]:
        """Maps a COVESA VSS signal path to VHAL and injects it."""
        if vss_path not in self.mappings:
            raise KeyError(f"Unknown VSS signal path: {vss_path}")

        meta = self.mappings[vss_path]
        prop_id = meta["vhal_property_id"]
        target_area = area_id if area_id is not None else meta.get("area_id", 0)
        conversion = meta.get("conversion")

        # Handle unit conversion if defined
        injected_value = value
        if conversion == "kmh_to_ms":
            # km/h to m/s
            injected_value = round(float(value) / 3.6, 2)
        elif conversion == "soc_percent_to_wh":
            # Convert percentage (0-100) to Watt-hours (Wh)
            injected_value = round((float(value) / 100.0) * (self.battery_capacity_kwh * 1000.0), 1)
        elif meta.get("data_type") == "boolean":
            injected_value = 1 if bool(value) else 0
        elif meta.get("unit") == "enum":
            enum_map = {}
            for k, v in meta.get("enum_values", {}).items():
                if k is True:
                    enum_map["ON"] = v
                    enum_map["TRUE"] = v
                elif k is False:
                    enum_map["OFF"] = v
                    enum_map["FALSE"] = v
                else:
                    enum_map[str(k).upper()] = v
            val_str = str(value).upper()
            if val_str in enum_map:
                injected_value = enum_map[val_str]
            elif value in enum_map.values():
                injected_value = value
            else:
                raise ValueError(f"Value '{value}' not found in enum for {vss_path}. Options: {list(enum_map.keys())}")

        start_t = time.perf_counter()
        output = self.inject_vhal_raw(
            prop_id,
            injected_value,
            target_area,
            data_type=meta.get("data_type", "int"),
        )
        latency_ms = round((time.perf_counter() - start_t) * 1000, 2)

        return {
            "vss_path": vss_path,
            "vhal_property_id": prop_id,
            "vhal_property_name": meta["vhal_property_name"],
            "raw_input": value,
            "injected_value": injected_value,
            "area_id": target_area,
            "latency_ms": latency_ms,
            "response": output
        }

    # Convenience domain helpers
    def set_gear(self, gear: str) -> Dict[str, Any]:
        """Sets transmission gear: PARK, REVERSE, DRIVE, NEUTRAL."""
        gear_upper = gear.upper()
        if not gear_upper.startswith("GEAR_"):
            gear_upper = f"GEAR_{gear_upper}"
        return self.inject_vss("Vehicle.Powertrain.Transmission.SelectedGear", gear_upper)

    def set_speed(self, speed_kmh: float) -> Dict[str, Any]:
        """Sets vehicle speed in km/h."""
        return self.inject_vss("Vehicle.Speed", speed_kmh)

    def set_battery_level(self, soc_percent: float) -> Dict[str, Any]:
        """Sets state of charge percentage (0-100%)."""
        return self.inject_vss("Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed", soc_percent)

    def set_parking_brake(self, engaged: bool) -> Dict[str, Any]:
        """Engages or disengages parking brake."""
        return self.inject_vss("Vehicle.Chassis.ParkingBrake.IsEngaged", engaged)

    def set_charging(self, port_open: bool, cable_connected: bool) -> list[Dict[str, Any]]:
        """Sets EV charge port and connection state."""
        res1 = self.inject_vss("Vehicle.Powertrain.TractionBattery.Charging.ChargePortFlap", port_open)
        res2 = self.inject_vss("Vehicle.Powertrain.TractionBattery.Charging.IsChargingCableConnected", cable_connected)
        return [res1, res2]

    def set_hvac_temperature(self, temp_celsius: float, row: int = 49) -> Dict[str, Any]:
        """Sets cabin HVAC temperature setpoint (default area_id=49 for AOSP Driver HVAC zone)."""
        return self.inject_vss("Vehicle.Cabin.HVAC.Station.Row1.Driver.Temperature", temp_celsius, area_id=row)
