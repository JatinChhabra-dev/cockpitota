# CORA — Complete End-to-End Flow & File-by-File Documentation

> **Compliance Notice:** *Evidence prepared for SUMS review. Not a type-approval or certification decision.*  
> Fictional OEM: **Aurelia Motors** · Target Regulation Alignment: **UNECE R156**

---

## Part 1 — Fresh End-to-End Run Flow (9-Beat Live Demo)

### Step 0 — Start Services (Clean Slate)
1. **Verify `.env`** (`cockpit-ota/.env`):
   ```env
   AI_PROVIDER=gemini
   GEMINI_API_KEY=<your_real_gemini_key>
   GEMINI_MODEL=gemini-2.5-flash
   ```
2. *(Optional)* **Start Real Eclipse hawkBit 1.0** in Docker:
   ```powershell
   docker run -d --name cora-hawkbit -p 8080:8080 hawkbit/hawkbit-update-server:latest
   ```
   *(If skipped, M4 runs automatically in `LOCAL_MIRROR` mode with identical rollout logic.)*
3. **Terminal 1 — Start Unified Backend API (`:8001`)**:
   ```powershell
   cd "C:\Users\JatinChhabra\Desktop\Cockpit & OTA\cockpit-ota"
   python -m uvicorn fleet.manager:app --port 8001 --reload
   ```
4. **Terminal 2 — Start React Operations Console (`:3000`)**:
   ```powershell
   cd "C:\Users\JatinChhabra\Desktop\Cockpit & OTA\cockpit-ota\console"
   npm run dev
   ```
5. Open **`http://localhost:3000`** in Chrome/Edge.

---

### The 9-Beat End-to-End Walkthrough (Spec §14)

| Beat | Console Tab / Action | What Happens Under the Hood |
|---|---|---|
| **1. Set the Scene** | **`Virtual Fleet (M1)`** & **`R156 Dossier (M7)`** | Shows the 3 target variants (`VAR-A` 1920×1080 `en-US`, `VAR-B` 1080×1920 Portrait, `VAR-C` 1920×1080 `de-DE`) and registered releases (`v1.0`, `v1.1`, `v1.1-fix`). |
| **2. AI Writes Tests** | **`AI Review (M6)`** → Click **Propose Tests (v1.1)** → Click **Approve** | Gemini reads `apps/release_notes_v1.1.yaml` + `signals/scenarios/` and generates 6 runnable YAML test proposals (including *"Reverse gear while charging menu open"*). Proposals remain gated until an engineer clicks **Approve**; `AIRecord` with prompt SHA-256 is written to `evidence/ai_records.json`. |
| **3. Fleet Boots** | **`Virtual Fleet (M1)`** → Select `Build: v1.0` → Click **Launch All 3 in Parallel** (or VAR-A + VAR-B) | `fleet/avd_backend.py` boots the AAOS emulators, enforces display geometry (`wm size`), sets `persist.sys.locale` & `debug.cora.*` flags, conditionally installs `APP-1` + `APP-2` if not already at `v1.0`, and auto-launches **Aurelia EV** on screen. |
| **4. Drive Cycle** | **`Signal Control Deck (M2)`** or **`Scenario Replay (M2)`** | Injects COVESA VSS signals into AIDL `FakeVehicleHardware` (`--set`). Setting `DRIVE` + `50 km/h` updates the live digital speedometer in `APP-1` and engages Android `CarUxRestrictions` (disabling keyboard/schedule edits). |
| **5. Run Baseline (`v1.0`) & Candidate (`v1.1`) — The Catch** | **`Equivalence & Gate (M5)`** → Run **`v1.0` Live**, then Run **`v1.1` Live** → Click **Evaluate Gate** | `engine/runner.py` executes `SC-01..SC-04` live on each emulator, capturing `uiautomator` XML trees, top-window z-order, VHAL read-backs, PNG screenshots, and `logcat`. `engine/differ.py` diffs `v1.1` vs `v1.0` using Pillow + `release_notes_v1.1.yaml`. **Result:** `VAR-A = PASS`, **`VAR-B = BLOCK`** (charging modal suppressed `APP-2` Rear-view + `[DEFECT_M3_FR4]`). Click **Triage VAR-B Failure** in **`AI Review (M6)`** — Gemini explains root cause (*APP-1 portrait modal focus*) with real screenshot & logcat refs. |
| **6. Approval Impact** | **`Equivalence & Gate (M5)`** | Release Gate sets **`RXSWIN-IMPACT: YES (HOMOLOGATION)`** for `APP-2 (RXSWIN-AURELIA-RVC-158)` and sets `ota_eligible = false` (blocking M4 OTA creation with HTTP 403). |
| **7. Fix & Equivalence** | **`Equivalence & Gate (M5)`** → Select **`v1.1-fix`** → Click **Run v1.1-fix Live** → **Evaluate Gate** | `v1.1-fix` restores `APP-2` Rear-view `< 500 ms` on `VAR-B` while keeping `CHG-101..103`. Equivalence report shows **only `DECLARED` / `COSMETIC` diffs (`0 UNEXPLAINED`)** → Gate flips to **`PASS (OTA Eligible)`**. |
| **8. Staged OTA Rollout** | **`OTA & Ledger (M4)`** → Optionally simulate `SC-01` (50 km/h) or `SoC 20%` on a cockpit → Click **Push OTA to Live Cockpits** → Park/Charge → Click **Re-check Preconditions (Tick)** | `ota/engine.py` runs 2-group rollout (`Group 1 Canary` → auto-advance → `Group 2 Fleet`). `ota/agent.py` verifies SHA-256 + signature (`M4-FR3`), checks live VHAL preconditions (`GEAR_PARK`, `speed == 0`, `SoC >= 30%`, `M4-FR2`), defers ineligible vehicles, installs verified APK via ADB, auto-relaunches **Aurelia EV**, and records pre/post versions in `evidence/ota_ledger.json` (and syncs to live hawkBit `:8080` if Docker is up). |
| **9. The Evidence Dossier** | **`R156 Dossier (M7)`** → Select **`v1.1-fix`** → Enter Reviewer Name → Click **Open HTML Dossier** or **Download R156 PDF** | `dossier/generator.py` assembles all **9 UNECE R156 sections** purely from pipeline records (`manifest.json`, `release_notes_v1.1.yaml`, `components.yaml`, `variants.yaml`, `runs/`, `gates/`, `ai_records.json`, `ota_ledger.json`), computes a deterministic SHA-256 integrity hash, and exports HTML/JSON/PDF in `< 3 s`. |

---

## Part 2 — Complete File-by-File Repository Documentation

### Root Configuration
| File | Purpose |
|---|---|
| `README.md` | Project overview, prerequisites, quickstart, acceptance test commands, and API reference. |
| `requirements.txt` | Python dependencies (`fastapi`, `uvicorn`, `pydantic`, `pyyaml`, `pillow`, `pytest`, etc.). |
| `.env` *(git-ignored)* | Local secrets (`AI_PROVIDER=gemini`, `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-2.5-flash`). |
| `.env.example` | Safe template showing required `.env` variables for teammates. |
| `.gitignore` | Excludes `.env`, `node_modules/`, `dist/`, `__pycache__/`, `apps/.build_tmp/`, signing keystores (`.jks`), and runtime `evidence/` artifacts. |

---

### Module 1 — `fleet/` (Virtual Cockpit Fleet Manager)
| File | Purpose |
|---|---|
| `fleet/variants.yaml` | Declarative specs for `VAR-A` (1920×1080 `en-US`), `VAR-B` (1080×1920 Portrait `en-US`), and `VAR-C` (1920×1080 `de-DE`, `EU_DATA_CONSENT_PROMPT=on`). |
| `fleet/models.py` | Pydantic models (`FleetInstance`, `InstanceStatus`, `LaunchRequest`, `LaunchResponse`, `VariantConfig`). |
| `fleet/avd_backend.py` | Local Android Studio AVD driver (cloud-swappable for Cuttlefish): allocates ADB ports (`5554/5556/5558`), boots/adopts AVDs, applies `wm size` & `persist.sys.locale` & `debug.cora.*` flags, provides `is_device_alive()` liveness check, and `ensure_demo_apps()` conditional APK installer + auto-launcher. |
| `fleet/stream.py` | Screen streaming & PNG screenshot capture helper (`adb exec-out screencap -p`, optional `scrcpy`). |
| `fleet/manager.py` | Central FastAPI application (`:8001`) hosting M1 Fleet routes, real-time ADB liveness reconciliation, per-serial `VhalInjector` cache, and mounting M2 (`signals`), M3 (`apps.companion`), M4 (`ota`), M5 (`engine`), M6 (`ai`), and M7 (`dossier`) routers. |
| `fleet/test_m1_acceptance.py` | M1 acceptance test suite (29 checks across all 3 live variants in parallel). |

---

### Module 2 — `signals/` (Vehicle Signal Simulator)
| File | Purpose |
|---|---|
| `signals/vss_vhal_map.yaml` | Data-driven COVESA VSS 4.x → AOSP VHAL property mapping (all 9 Appendix A signals, unit conversions `km/h → m/s` and `SoC % → Wh`, AOSP enums, HVAC zone `49`). |
| `signals/injector.py` | `VhalInjector`: translates VSS paths to VHAL IDs and writes directly into AIDL `FakeVehicleHardware` (`dumpsys android.hardware.automotive.vehicle.IVehicle/default --set`) so continuous properties persist across 1 Hz refreshes, with `cmd car_service inject-vhal-event` fallback and per-device lock serialization. |
| `signals/replay.py` | `ScenarioReplayController`: `time.monotonic()`-anchored deterministic scenario replay (M2-FR4 ±100 ms), speed factor support, and append-only JSON trace persistence to `evidence/traces/`. |
| `signals/can_importer.py` | Converts DBC-decoded CAN CSV logs (`sample_can_log.csv`) into VSS scenario YAML (`M2-FR5`). |
| `signals/router.py` | REST endpoints: `GET /v1/scenarios`, `GET /v1/scenarios/{id}`, `POST /v1/scenarios/{id}/replay`. |
| `signals/scenarios/sc01..sc05.yaml` | The 5 standard spec scenarios: `SC-01` Urban drive, `SC-02` Park & charge, `SC-03` Reverse with menu open, `SC-04` Remote climate, `SC-05` Low-battery park. |
| `signals/test_m2_acceptance.py` | M2 acceptance test suite (17 checks: catalogue, VHAL map, CAN CSV import, live SC-03/SC-02/SC-01 replay). |

---

### Module 3 — `apps/` (Demo OEM Applications)
| File | Purpose |
|---|---|
| `apps/app-ev/AndroidManifest.xml` | Manifest for `APP-1` (`com.aurelia.ev`) with AAOS `CAR_SPEED`, `CAR_POWERTRAIN`, `CAR_ENERGY`, `CAR_INFO`, `CONTROL_CAR_CLIMATE` permissions and `RemoteCommandReceiver`. |
| `apps/app-ev/src/main/kotlin/com/aurelia/ev/MainActivity.kt` | Genuine Kotlin AAOS app binding to `CarPropertyManager` & `CarUxRestrictionsManager`: live digital speedometer, gear badge, EV/ICE powertrain detector (`INFO_FUEL_TYPE`), battery SoC gauge, charge port/cable status, HVAC card, EU consent banner, charging schedule modal, and `v1.1` planted portrait modal defect (`M3-FR4`). |
| `apps/app-ev/src/main/kotlin/com/aurelia/ev/RemoteCommandReceiver.kt` | Broadcast receiver for deterministic `ACTION_OPEN_CHARGING_MODAL`, `ACTION_CLOSE_CHARGING_MODAL`, and `ACTION_REMOTE_CLIMATE` commands. |
| `apps/app-ev/src/main/kotlin/com/aurelia/ev/BuildVariantConfig.kt` | Compile-time flavor flags (`v1.0`, `v1.1`, `v1.1-fix`) injected during build. |
| `apps/app-ev/src/main/res/values/{ids,strings}.xml` & `values-de/strings.xml` | Stable Android resource IDs (for M5 `uiautomator` diffing) plus `en-US` and `de-DE` localized strings. |
| `apps/app-rearview/AndroidManifest.xml` & `RearViewActivity.kt` | Standalone `APP-2` (`com.aurelia.rearview`) full-screen reversing overlay with trajectory guidelines, warning banner, and live render latency measurement (`< 500 ms`, logged as `[RENDERED]`). |
| `apps/companion/router.py` | `APP-3` Mock Vehicle Cloud REST router (`POST /v1/cloud/vehicles/{id}/climate`, `/charge-schedule`, `GET /commands`) for `SC-04`. |
| `apps/build_apks.ps1` | Zero-download local Kotlin AAOS build script (`aapt2`, `javac`, `K2JVMCompiler`, `d8`, `zipalign`, `apksigner`) outputting all 4 signed APKs + SHA-256 `apps/dist/manifest.json`. |
| `apps/dist/*.apk` & `manifest.json` | Compiled, RSA-signed APKs (`aurelia-ev-v1.0.apk`, `v1.1.apk`, `v1.1-fix.apk`, `aurelia-rearview-v1.0.apk`) and their SHA-256 manifest. |
| `apps/release_notes_v1.1.yaml` & `.md` | Machine-readable (`DeclaredChange` schema: `CHG-101..103`) and human-readable release notes for `v1.1`. |
| `apps/test_m3_acceptance.py` | M3 acceptance test suite (17 checks verifying `v1.0`, `v1.1` VAR-B defect, `v1.1-fix`, and `SC-04`). |

---

### Module 4 — `ota/` (Staged OTA Rollout & R156 Ledger)
| File | Purpose |
|---|---|
| `ota/models.py` | Pydantic models (`Campaign`, `RolloutGroup`, `UpdateRecord`, `AgentState`, `PreconditionSnapshot`). |
| `ota/signing.py` | SHA-256 digest & cryptographic HMAC-SHA256 signing/verification (`M4-FR3` tamper rejection). |
| `ota/hawkbit_client.py` | Real Eclipse hawkBit 1.0 Management REST API adapter (`softwaremodules`, `distributionsets`, `targets`, `rollouts`) with transparent `LOCAL_MIRROR` fallback when Docker is offline. |
| `ota/agent.py` | Update Agent state machine (`IDLE → VERIFYING → WAIT_PRECOND → INSTALLING → REPORTING`): verifies signature, checks live VHAL (`GEAR_PARK`, `speed == 0`, `SoC >= 30%`), installs APK via ADB, auto-relaunches `APP-1`, records pre/post versions, and rolls back on failure. |
| `ota/engine.py` | Staged 2-group rollout orchestrator (`Group 1 Canary` → auto-advance at 100% → `Group 2 Fleet`), pause/resume/cancel, live ADB vehicle sync + optional 10-vehicle M1-FR7 scale fleet, and append-only `evidence/ota_ledger.json`. |
| `ota/router.py` | REST endpoints: `POST/GET /v1/campaigns`, `/tick`, `/pause`, `/resume`, `/cancel`, `GET /v1/vehicles`, `GET /v1/vehicles/{id}/ledger`, `POST /v1/vehicles/{id}/state`. |
| `ota/test_m4_acceptance.py` | M4 acceptance test suite (17 checks: gate blocking, 10%→100%, SC-01/SC-05 deferrals & recovery, tamper rejection, live ADB OTA install). |

---

### Module 5 — `engine/` (Test & Equivalence Engine + Release Gate)
| File | Purpose |
|---|---|
| `engine/components.yaml` | Software Component Register (`APP-1`, `APP-2`, `APP-3`) with `approval_relevant` tags and `RXSWIN` refs (`RXSWIN-AURELIA-RVC-158`). |
| `engine/models.py` | Pydantic models (`RunRecord`, `TestResult`, `TraceStep`, `UiNode`, `Difference`, `EquivalenceReport`, `GateDecision`). |
| `engine/trace.py` | Real ADB Trace Recorder: captures `uiautomator dump` XML + SHA-256 `ui_hash`, `dumpsys activity` top z-order, VHAL property read-backs, PNG screenshots, and `logcat` windows. |
| `engine/runner.py` | Parallel live scenario runner executing `SC-01` (UX lock), `SC-02` (EV charging), `SC-03` (Rear-view `< 500 ms`), `SC-04` (HVAC), and `VAR-C` localisation with flaky-test quarantine (`M5-FR8`) and JUnit XML + JSON trace export to `evidence/runs/`. |
| `engine/differ.py` | Core CORA IP: step-by-step diff of UI trees, safety z-order (never `COSMETIC`), VHAL properties, timings, and real **Pillow** pixel-diff masks (`evidence/diffs/`), classifying every difference as `DECLARED`, `COSMETIC`, or `UNEXPLAINED`. |
| `engine/gate.py` | Spec Figure 3 idempotent per-variant Release Gate + parallel `RXSWIN-impact` evaluator, persisting decisions to `evidence/gates/`. |
| `engine/router.py` | REST endpoints: `POST/GET /v1/runs`, `GET /v1/runs/{id}`, `GET /v1/releases/{id}/equivalence`, `POST /v1/releases/{id}/gate`, `GET /v1/components`. |
| `engine/test_m5_acceptance.py` | Live M5 acceptance test suite (18 checks running `v1.0` → `v1.1` VAR-B BLOCK → `v1.1-fix` PASS → undeclared string block). |

---

### Module 6 — `ai/` (AI Layer & Human Review Queue)
| File | Purpose |
|---|---|
| `ai/adapter.py` | Provider-agnostic LLM adapter loading `.env` for live **Google Gemini** (`gemini-2.5-flash` via REST), Anthropic Claude, or offline deterministic fallback. |
| `ai/models.py` | Pydantic models (`TestProposal`, `ReviewProposalRequest`, `TriageRequest`, `VisualClassifyRequest`, `AIRecord`). |
| `ai/prompts/{test_gen_v1,triage_v1,visual_diff_v1}.txt` | Versioned prompt registry templates hashed into every `AIRecord`. |
| `ai/generator.py` | Generates ≥ 5 runnable YAML test proposals from `release_notes_v1.1.yaml` + scenarios (including *"Reverse while charging menu open"*). |
| `ai/triage.py` | Formats real M5 failure bundles (UI tree, `logcat`, screenshot URI) and invokes `LLMAdapter` to diagnose root cause & owner. |
| `ai/visual_classifier.py` | Classifies visual diffs into `DEFECT`, `DECLARED`, or `COSMETIC`. |
| `ai/store.py` & `ai/router.py` | Manages human approval queue (`POST /v1/test-proposals/{id}/review`), pulls real M5 failure evidence, persists `evidence/ai_records.json`, and supports `POST /v1/ai/toggle` (proving M5 gate works with AI off). |
| `ai/test_m6_acceptance.py` | M6 acceptance test suite (proposals, human review, real VAR-B triage, visual classification, audit log, AI-off independence). |

---

### Module 7 — `dossier/` (Evidence Store & UNECE R156 Dossier)
| File | Purpose |
|---|---|
| `dossier/generator.py` | Assembles all **9 UNECE R156 sections** purely from pipeline records, computes dossier SHA-256 integrity hash, collects measured POC metrics (`M7-FR7`), and renders JSON, Ferfier-branded HTML, and standards-compliant PDF (`%PDF-1.4`). |
| `dossier/router.py` | REST endpoints: `GET/POST /v1/releases`, `GET /v1/releases/{id}`, `GET /v1/releases/{id}/dossier?format=json\|html\|pdf`, `GET /v1/metrics`. |
| `dossier/test_m7_acceptance.py` | M7 acceptance test suite (12 checks verifying all 9 sections, SHA-256, SUMS disclaimer, HTML, and `< 30 s` PDF export). |

---

### Operations Console — `console/` (React 18 + TypeScript + Vite)
| File | Purpose |
|---|---|
| `console/index.html` & `vite.config.ts` | Vite entry point and proxy routing `/v1`, `/health`, `/evidence` → `http://localhost:8001`. |
| `console/src/index.css` | Zero-dependency Ferfier dark automotive CSS design system (Navy `#13294C`, Royal Blue `#2E74C9`, Crimson `#D81F2D`). |
| `console/src/api.ts` | Strongly-typed REST client covering all M1–M7 backend endpoints. |
| `console/src/App.tsx` & `components/Header.tsx` | Main shell with mandatory SUMS compliance banner, live API health indicator, active fleet counter, and 7-tab navigation. |
| `console/src/components/FleetTab.tsx` | **M1** — Variant cards (`VAR-A/B/C`), build selector (`v1.0`/`v1.1`/`v1.1-fix`), parallel launch, live cockpit cards, screenshots, teardown. |
| `console/src/components/SignalsTab.tsx` | **M2** — Interactive gear (`P/R/N/D`), debounced speed & battery SoC sliders, ignition, parking brake, charge port/cable, HVAC controls, telemetry feed. |
| `console/src/components/ScenariosTab.tsx` | **M2** — `SC-01..SC-05` scenario catalogue, speed multiplier (`1x–10x`), and live replay trace viewer. |
| `console/src/components/OtaTab.tsx` | **M4** — Live AAOS cockpit OTA rollout launcher (with optional 10-vehicle scale toggle), hawkBit status badge, tamper test, precondition simulator, pause/resume/cancel, R156 vehicle ledger. |
| `console/src/components/EquivalenceTab.tsx` | **M5** — Live suite runner, Release Gate & `RXSWIN-IMPACT` banner, per-variant matrix, and filterable `DECLARED`/`COSMETIC`/`UNEXPLAINED` diff table. |
| `console/src/components/AiReviewTab.tsx` | **M6** — AI enable/disable toggle, Gemini test proposal review queue (`Approve`/`Reject`), VAR-B failure triage card, and `AIRecord` SHA-256 audit table. |
| `console/src/components/DossierTab.tsx` | **M7** — Measured metrics cards, release registry, reviewer sign-off input, 9-section R156 preview, and one-click HTML / JSON / PDF export. |

---

### Infrastructure & Docs — `infra/` & `docs/`
| File | Purpose |
|---|---|
| `infra/docker-compose.yml` | Local Docker Compose stack for PostgreSQL 16 (`:5432`) and Eclipse hawkBit 1.0 (`:8080`). |
| `docs/adr/ADR-01..02.md` | Architecture Decision Records (Android AVD → Cuttlefish target; AIDL `FakeVehicleHardware` VHAL injection). |
| `docs/spikes/S1..S4` & `scripts/` | Phase 0 spike specs, PowerShell/Python verification scripts, and measured baseline results. |
