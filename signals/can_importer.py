"""
CAN / DBC-decoded CSV Importer (M2-FR5)
Translates recorded vehicle bus logs (CSV format) into standardized COVESA VSS scenario YAML.
"""

import csv
import os
from typing import Dict, List, Optional
import yaml

# Standard CAN message/signal aliases to COVESA VSS paths
DEFAULT_CAN_VSS_ALIASES = {
    # Powertrain / Transmission
    "GearPosition": "Vehicle.Powertrain.Transmission.SelectedGear",
    "TransmissionGear": "Vehicle.Powertrain.Transmission.SelectedGear",
    "CurrentGear": "Vehicle.Powertrain.Transmission.CurrentGear",
    "GEAR": "Vehicle.Powertrain.Transmission.SelectedGear",
    
    # Speed & Dynamics
    "VehicleSpeed": "Vehicle.Speed",
    "WheelSpeed": "Vehicle.Speed",
    "SPEED": "Vehicle.Speed",
    "Vehicle_Speed_KMH": "Vehicle.Speed",
    
    # Chassis & Brake
    "ParkingBrakeState": "Vehicle.Chassis.ParkingBrake.IsEngaged",
    "Handbrake": "Vehicle.Chassis.ParkingBrake.IsEngaged",
    "EPB_Status": "Vehicle.Chassis.ParkingBrake.IsEngaged",
    
    # Battery & EV
    "BatterySOC": "Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed",
    "StateOfCharge": "Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed",
    "HV_Battery_SOC": "Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed",
    "ChargePortFlap": "Vehicle.Powertrain.TractionBattery.Charging.ChargePortFlap",
    "ChargeCableConnected": "Vehicle.Powertrain.TractionBattery.Charging.IsChargingCableConnected",
    
    # HVAC
    "HVAC_DriverTempSet": "Vehicle.Cabin.HVAC.Station.Row1.Driver.Temperature",
    "DriverSetTemp": "Vehicle.Cabin.HVAC.Station.Row1.Driver.Temperature"
}

def import_can_csv_to_scenario(
    csv_path: str,
    output_yaml_path: Optional[str] = None,
    scenario_id: str = "SC-CAN-01",
    scenario_name: str = "Imported CAN Drive Trace",
    aliases: Optional[Dict[str, str]] = None
) -> Dict:
    """
    Reads a DBC-decoded CSV with headers like [timestamp, signal, value]
    and produces a valid CORA scenario YAML file.
    """
    alias_map = {**DEFAULT_CAN_VSS_ALIASES, **(aliases or {})}
    steps: List[Dict] = []
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize column keys
            normalized = {k.strip().lower(): v.strip() for k, v in row.items()}
            
            raw_t = normalized.get("time") or normalized.get("timestamp") or normalized.get("t")
            sig = normalized.get("signal") or normalized.get("signal_name") or normalized.get("name")
            val_str = normalized.get("value") or normalized.get("val")

            if not (raw_t and sig and val_str):
                continue
                
            t = round(float(raw_t), 2)
            
            # Map signal to VSS
            vss_signal = alias_map.get(sig, sig)
            
            # Type conversion
            try:
                if "." in val_str:
                    val = float(val_str)
                else:
                    val = int(val_str)
            except ValueError:
                # Boolean / String parsing
                if val_str.lower() in ["true", "on", "yes", "engaged", "open"]:
                    val = True
                elif val_str.lower() in ["false", "off", "no", "disengaged", "closed"]:
                    val = False
                else:
                    val = val_str

            steps.append({
                "t": t,
                "phase": f"can_t_{int(t)}s",
                "signal": vss_signal,
                "value": val,
                "description": f"CAN decoded event: {sig} = {val_str}"
            })

    # Sort steps by timestamp
    steps.sort(key=lambda s: s["t"])

    scenario_data = {
        "scenario_id": scenario_id,
        "name": scenario_name,
        "description": f"Imported from recorded CAN log: {os.path.basename(csv_path)}",
        "version": "1.0",
        "source": "CAN_CSV_IMPORT",
        "duration_seconds": steps[-1]["t"] if steps else 0.0,
        "steps": steps
    }

    if output_yaml_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_yaml_path)), exist_ok=True)
        with open(output_yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(scenario_data, f, sort_keys=False)

    return scenario_data
