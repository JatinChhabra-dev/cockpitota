# ADR-01: Android Build Target for Local POC

**Date**: 2026-11-16  
**Status**: ✅ DECIDED (confirmed by S1 spike)

## Decision

**Use Android AVD with Automotive system image (API 33, x86_64) for the local phase.**  
Migrate to Cuttlefish on GCP in the cloud phase (post-G7).

## Measured Results (S1)

| Metric | Value |
|--------|-------|
| Boot time | **46 seconds** |
| SDK path | `C:\Users\JatinChhabra\AppData\Local\Android\Sdk` |
| System image | Android Automotive with Google APIs x86_64 (API 33) |
| `ro.build.characteristics` | `automotive` ✅ |
| `ro.product.locale` | `en-US` ✅ |

## Context

The spec targets Cuttlefish on Google Cloud. Locally on Windows, two options exist:

| Option | Pros | Cons |
|--------|------|------|
| Android AVD (Automotive) ✅ | Native Windows, 46s boot, no WSL2 | Slightly different from Cuttlefish |
| Cuttlefish via WSL2 | Closest to cloud target | Requires Linux/WSL2, slow on Windows |

## Consequences

- S2 spike must verify VHAL injection works against AVD (gRPC or adb property fallback)
- Fleet manager service wraps `emulator -avd` commands
- Cloud migration: replace fleet manager's emulator backend with Cuttlefish launcher; API stays identical
