# CORA — Cockpit & OTA Release Assurance (POC)

> **Compliance Notice:** *Evidence prepared for SUMS review. Not a type-approval or certification decision.*  
> Fictional OEM: **Aurelia Motors** · Target Regulation Alignment: **UNECE R156**

Local-first implementation of the **Ferfier Cockpit & OTA Release Assurance (CORA)** proof of concept — a virtual Android Automotive OS (AAOS) release assurance twin with real VHAL signal injection, Kotlin OEM cockpit apps, staged OTA rollouts (Eclipse hawkBit 1.0), and an interactive React Operations Console.

---

## Current Progress & Module Status

| Phase / Module | Scope | Status | Verification |
|---|---|---|---|
| **Phase 0 — Spikes (S1–S4)** | AAOS boot, VHAL injection, hawkBit Docker, AI triage | Complete | All 4 spikes passed (`docs/spikes/`) |
| **M1 — Virtual Cockpit Fleet** | 3 parallel AAOS variants (`VAR-A`, `VAR-B`, `VAR-C`), Fleet REST API, ADB liveness sync | **Complete** | `29/29` checks passed (`fleet/test_m1_acceptance.py`) |
| **M2 — Vehicle Signal Simulator** | COVESA VSS → AOSP VHAL (`FakeVehicleHardware`), `SC-01`..`SC-05`, CAN CSV importer, monotonic replay | **Complete** | `17/17` checks passed (`signals/test_m2_acceptance.py`) |
| **M3 — Demo OEM Applications** | Kotlin AAOS `APP-1` (Aurelia EV), `APP-2` (Rear-view `< 500 ms`), `APP-3` (Mock Cloud), `v1.0` / `v1.1` (planted VAR-B defect) / `v1.1-fix` | **Complete** | `17/17` checks passed (`apps/test_m3_acceptance.py`) |
| **M4 — Staged OTA Rollout** | Eclipse hawkBit 1.0 adapter, 2-group rollout (`10% → 100%`), SHA-256 signing, VHAL preconditions (`parked + SoC ≥ 30%`), R156 ledger | **Complete** | `17/17` checks passed (`ota/test_m4_acceptance.py`) |
| **Console (M1/M2/M4 UI)** | React 18 + TypeScript + Vite dashboard (`Virtual Fleet`, `Signal Control Deck`, `Scenario Replay`, `OTA & Ledger`) | **Complete** | Verified live on `http://localhost:3000` |
| **M5 — Test & Equivalence Engine** | Scenario runner, trace differ (`DECLARED`/`COSMETIC`/`UNEXPLAINED`), Release Gate, RXSWIN-impact | Next | — |
| **M6 — AI Layer** | Test proposal generator, failure triage, visual-diff classifier | Planned | — |
| **M7 — Evidence Store & Dossier** | Full 9-screen console + one-click R156 HTML/PDF/JSON dossier export | Planned | — |

---

## Repository Structure

```text
cockpit-ota/
├── fleet/        # M1 — FastAPI Fleet Manager (:8001), AVD backend, variant configs (VAR-A/B/C)
├── signals/      # M2 — VSS->VHAL mapping, VhalInjector, deterministic replay, SC-01..SC-05, CAN CSV importer
├── apps/         # M3 — Kotlin AAOS apps (app-ev, app-rearview), APP-3 mock cloud, APK builder, release notes
├── ota/          # M4 — Eclipse hawkBit 1.0 adapter, Update Agent state machine, signing, staged rollout engine
├── console/      # React 18 + TypeScript + Vite Operations Console (:3000)
├── infra/        # Docker Compose (Postgres 16 + Eclipse hawkBit 1.0)
├── ai/           # M6 — AI adapter & triage prompts (Spike S4 baseline)
├── engine/       # M5 — Test & equivalence engine (upcoming)
├── evidence/     # Runtime screenshots, replay traces, R156 OTA ledger
└── docs/
    ├── adr/      # Architecture Decision Records (ADR-01, ADR-02)
    └── spikes/   # Phase 0 spike scripts & measured results
```

---

## Prerequisites

- **OS**: Windows 10/11 (32 GB RAM recommended for running all 3 AAOS AVDs simultaneously)
- **Python**: 3.12+ (`pip install -r requirements.txt`)
- **Node.js**: 18+ (for React Console)
- **Java**: OpenJDK 17+
- **Android Studio + Android SDK**:
  - Platforms `android-33` / `android-34` (with `optional/android.car.jar`) and `build-tools`
  - Three Android Automotive AVDs created in Android Studio Device Manager:
    - `AAOS-VAR-A` — 1920×1080 landscape (`en-US`, `EV_CHARGE_SCHEDULE=on`)
    - `AAOS-VAR-B` — 1080×1920 portrait (`en-US`, `EV_CHARGE_SCHEDULE=on`, planted defect target)
    - `AAOS-VAR-C` — 1920×1080 landscape (`de-DE`, `EU_DATA_CONSENT_PROMPT=on`)
- **Docker Desktop** *(optional for local dev; required for live Eclipse hawkBit 1.0 UI)*

---

## Quickstart

### 1. Start the Backend API (Fleet Manager + Signals + Mock Cloud + OTA)
```powershell
cd cockpit-ota
pip install -r requirements.txt
python -m uvicorn fleet.manager:app --port 8001 --reload
```

### 2. Start the React Operations Console
```powershell
cd cockpit-ota\console
npm install
npm run dev
```
Open **`http://localhost:3000`** in your browser.

### 3. Build Module 3 Kotlin AAOS APKs *(optional — re-run after Kotlin edits)*
```powershell
cd cockpit-ota\apps
.\build_apks.ps1
```
Produces signed APKs + SHA-256 manifest in `apps/dist/`:
- `aurelia-ev-v1.0.apk` (Baseline)
- `aurelia-ev-v1.1.apk` (Candidate with `CHG-101..103` + planted `VAR-B` portrait modal regression)
- `aurelia-ev-v1.1-fix.apk` (Fix build removing only the regression)
- `aurelia-rearview-v1.0.apk` (Rear-view stand-in overlay)

### 4. Start Real Eclipse hawkBit 1.0 *(optional)*
Without Docker, the OTA engine runs in `LOCAL_MIRROR` mode automatically. To connect to a live hawkBit server (`http://localhost:8080`, credentials `admin` / `admin`):
```powershell
# Standalone hawkBit (embedded H2 DB — fastest for local demos)
docker run -d --name cora-hawkbit -p 8080:8080 hawkbit/hawkbit-update-server:latest

# Or full Compose stack (Postgres 16 + hawkBit)
docker compose -f infra/docker-compose.yml up -d
```

---

## Running Automated Acceptance Tests

With Fleet Manager running on port `8001`:

```powershell
cd cockpit-ota

# Module 1 — Three-Variant Virtual Cockpit Fleet (29 checks)
python fleet\test_m1_acceptance.py

# Module 2 — Vehicle Signal Simulator & Deterministic Replay (17 checks)
python signals\test_m2_acceptance.py

# Module 3 — Demo OEM Apps: v1.0, v1.1 VAR-B Defect, v1.1-fix, SC-04 Cloud (17 checks)
python apps\test_m3_acceptance.py

# Module 4 — Staged OTA Rollout, Preconditions, Tamper Rejection, R156 Ledger (17 checks)
python ota\test_m4_acceptance.py
```

---

## Key REST API Endpoints (`:8001`)

| Module | Endpoint | Purpose |
|---|---|---|
| **M1** | `GET /v1/fleet/variants` | List `VAR-A`, `VAR-B`, `VAR-C` definitions |
| **M1** | `POST /v1/fleet/instances` | Boot AAOS variant(s) with conditional app auto-install |
| **M1** | `GET /v1/fleet/instances` | List live instances with real-time ADB liveness sync |
| **M1** | `DELETE /v1/fleet/instances/{id}` | Tear down instance cleanly |
| **M1** | `POST /v1/fleet/instances/{id}/screenshot` | Capture cockpit screen to `evidence/screenshots/` |
| **M2** | `POST /v1/fleet/instances/{id}/signals` | Inject VSS signal directly into VHAL `FakeVehicleHardware` |
| **M2** | `GET /v1/scenarios` / `POST /v1/scenarios/{id}/replay` | Browse & deterministically replay `SC-01`..`SC-05` |
| **M3** | `POST /v1/cloud/vehicles/{id}/climate` | APP-3 Mock Vehicle Cloud remote HVAC command (`SC-04`) |
| **M4** | `POST /v1/campaigns` / `POST /v1/campaigns/{id}/tick` | Launch & advance staged `10% → 100%` OTA rollout |
| **M4** | `POST /v1/campaigns/{id}/pause\|resume\|cancel` | Campaign lifecycle controls |
| **M4** | `GET /v1/vehicles?mode=live\|all` | Inspect live ADB cockpits (or 10-vehicle scale fleet) |
| **M4** | `GET /v1/vehicles/{id}/ledger` | Per-vehicle R156 pre/post version update ledger |

---

## Architecture Decision Records (ADRs)

| ADR | Decision |
|---|---|
| [ADR-01](docs/adr/ADR-01-android-build-target.md) | Android build target: Local Android Studio AAOS AVDs (API 33/34) → GCP Cuttlefish in cloud phase |
| [ADR-02](docs/adr/ADR-02-vhal-injection-route.md) | VHAL injection via AIDL `dumpsys android.hardware.automotive.vehicle.IVehicle/default --set` (persists across 1 Hz continuous VHAL refresh) with `cmd car_service inject-vhal-event` fallback |
