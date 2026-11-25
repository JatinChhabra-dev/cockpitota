# ADR-02: Vehicle HAL (VHAL) Signal Injection Route

**Date**: 2026-11-16  
**Status**: Accepted / Proposed for POC  
**Deciders**: Tech Lead, QE Automation Engineer

## Context
The Cockpit & OTA Release Assurance system must inject realistic vehicle signals (speed, gear, battery state of charge, HVAC, charging status) into running AAOS cockpits to execute automated scenarios (SC-01 through SC-05) and enforce OTA preconditions.

The candidate routes investigated in Spike S2:
1. **gRPC VHAL (`GRPCVehicleHardware`)**: Direct gRPC client to an emulated vehicle hardware service.
   - *Pros*: Matches AOSP virtualization reference platform in modern cloud builds.
   - *Cons*: On local Windows AVD images, the gRPC port is often not exposed or requires custom AOSP emulator builds with gRPC flags enabled.
2. **`cmd car_service inject-vhal-event` via ADB**: Built-in Android Automotive command line injection exposed by the platform CarService.
   - *Pros*: Native to all official Google AAOS emulator system images (API 33, 34); zero compilation or extra daemons required; sub-50ms latency; supports property ID, area ID, and values.
   - *Cons*: Uses ADB transport layer.
3. **`dumpsys android.hardware.automotive.vehicle` debug overrides**:
   - *Pros*: Low-level HAL override.
   - *Cons*: Syntax varies between HIDL (@2.0) and AIDL implementations across Android versions.

## Decision
For the local POC phase, we adopt **`cmd car_service inject-vhal-event` via ADB** wrapped inside a clean Python abstraction layer (`signals/injector.py`).

The architecture uses a pluggable adapter interface:
```
                     +---------------------------------------+
                     |        Signal Injector Client         |
                     +---------------------------------------+
                                         |
                         +---------------+---------------+
                         |                               |
                 [ADB CarService]                 [gRPC VHAL]
                  (Local Phase)                  (Cloud / GCP)
```

## Consequences
- No extra background daemons or port forwardings required on Windows for S2, M1, and M2.
- The Python test runner (pytest) in M5 can trigger vehicle states synchronously.
- When migrating to Cuttlefish on GCP, the injector interface remains identical; only the backend transport switches to gRPC if configured.
