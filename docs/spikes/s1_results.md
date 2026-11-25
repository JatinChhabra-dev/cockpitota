# S1 Spike Results

> **Status**: ✅ PASSED — 2026-11-16

| Field | Value |
|-------|-------|
| AVD name | AAOS-VAR-A |
| Boot time (seconds) | **46** |
| ro.product.locale | en-US |
| ro.build.characteristics | automotive |
| ro.build.version.release | 13 |
| ro.build.version.sdk | 33 |
| ro.product.model | Android SDK built for x86_64 |
| ro.product.manufacturer | Google |
| Automotive confirmed | ✅ YES |
| Test date | 2026-11-16 15:54 |
| SDK path | C:\Users\JatinChhabra\AppData\Local\Android\Sdk |

## S1 Exit Criteria
- [x] AAOS AVD boots to launcher
- [x] `adb devices` shows instance connected  
- [x] Locale is en-US
- [x] `ro.build.characteristics` confirms `automotive`
- [x] Boot-to-launcher time measured: **46 seconds**
- [x] Screen visible (Android Studio emulator window)

## ADR-01 Decision: Android Build Target
> **Decision**: Android AVD with Automotive system image (API 33, x86_64) — Windows native  
> **Rationale**: 46s boot is well within demo tolerance; native Windows, no WSL2 needed; Cuttlefish deferred to cloud phase on GCP.
