# Spike S2 — VHAL Signal Injection

## Question
Can we inject VHAL properties (gear, speed, battery level) into the AAOS-VAR-A emulator, and does the cockpit UI react correctly?

## Exit Criteria
- [ ] `GEAR_SELECTION` can be set to REVERSE (value=2) via adb or gRPC
- [ ] `PERF_VEHICLE_SPEED` can be set to a non-zero value
- [ ] `EV_BATTERY_LEVEL` can be changed
- [ ] Setting gear to REVERSE causes the rear-view area to respond within 500 ms (measured)
- [ ] Injection method decided: **gRPC** vs **adb setprop / cmd car_service** fallback
- [ ] ADR-02 written

## Status: IN PROGRESS

---

## Background

AAOS exposes vehicle properties through the **Vehicle HAL (VHAL)**. The spec requires injecting signals like speed, gear, SoC into each cockpit so the UI reacts realistically. There are two injection routes:

| Route | How | Works on AVD? |
|-------|-----|--------------|
| gRPC VHAL | gRPC calls to `GRPCVehicleHardware` server inside the emulator | Depends on build — verify in spike |
| `cmd car_service` via adb | `adb shell cmd car_service inject-vhal-event` | ✅ Works on most AAOS builds |
| `dumpsys vehicle_hal` overrides | adb shell property overrides | Fallback |

## S2 Test Steps

### Method 1 — `cmd car_service` (try first, simplest)

```powershell
# Set gear to REVERSE (GEAR_SELECTION property ID = 289408000, value 2)
adb shell cmd car_service inject-vhal-event 0x11400a00 2 0

# Set speed to 30 km/h (PERF_VEHICLE_SPEED = 291504647, value 30.0)
adb shell cmd car_service inject-vhal-event 0x11600207 30.0 0

# Set EV battery level to 40% (EV_BATTERY_LEVEL = 291504905, value 40.0)
adb shell cmd car_service inject-vhal-event 0x11600309 40.0 0

# Set gear back to PARK (value 4)
adb shell cmd car_service inject-vhal-event 0x11400a00 4 0
```

> Property IDs are in hex: `0x11400a00` = 289408000 (GEAR_SELECTION)

### Method 2 — Read back to confirm

```powershell
# Check current property values
adb shell dumpsys android.hardware.automotive.vehicle
```

### VHAL Property ID Reference

| Signal | Decimal ID | Hex ID |
|--------|-----------|--------|
| GEAR_SELECTION | 289408000 | 0x11400a00 |
| CURRENT_GEAR | 289408001 | 0x11400a01 |
| PARKING_BRAKE_ON | 287310850 | 0x11200202 |
| PERF_VEHICLE_SPEED | 291504647 | 0x11600207 |
| IGNITION_STATE | 289408009 | 0x11400a09 |
| EV_BATTERY_LEVEL | 291504905 | 0x11600309 |
| EV_CHARGE_PORT_OPEN | 287310602 | 0x1120010a |
| EV_CHARGE_PORT_CONNECTED | 287310603 | 0x1120010b |
| HVAC_TEMPERATURE_SET | 358614275 | 0x15600503 |

Gear values: `GEAR_REVERSE=2`, `GEAR_PARK=4`, `GEAR_DRIVE=8`

## Run the S2 script

```powershell
# From cockpit-ota root (emulator must be running from S1):
.\docs\spikes\scripts\s2_vhal_check.ps1
```

## Notes
- AVD from S1 must be running when you run S2
- If `cmd car_service` is not available, try `dumpsys vehicle_hal` override route
- Record which properties accept injection vs. which are read-only
