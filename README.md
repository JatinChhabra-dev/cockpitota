# CORA — Cockpit & OTA Release Assurance (POC)

> **Compliance Notice:** *Evidence prepared for SUMS review. Not a type-approval or certification decision.*  
> Fictional OEM: **Aurelia Motors** · Target Regulation Alignment: **UNECE R156**

Local-first implementation of the **Ferfier Cockpit & OTA Release Assurance (CORA)** proof of concept — a virtual Android Automotive OS (AAOS) release assurance twin covering all **7 Modules (M1–M7)** with real VHAL signal injection, Kotlin OEM cockpit apps, Eclipse hawkBit 1.0 staged OTA rollouts, live ADB equivalence diffing, Gemini AI review/triage, and one-click UNECE R156 Release Dossier export.

For the complete 9-beat fresh-run walkthrough and file-by-file documentation, see **[docs/ARCHITECTURE_AND_RUNBOOK.md](docs/ARCHITECTURE_AND_RUNBOOK.md)**.

---

## Complete POC Status (All 7 Modules Gate-Passed)

| Phase / Module | Scope | Status | Verification |
|---|---|---|---|
| **Phase 0 — Spikes (S1–S4)** | AAOS boot, VHAL injection, hawkBit Docker, AI triage | **Complete** | `4/4` spikes passed (`docs/spikes/`) |
| **M1 — Virtual Cockpit Fleet** | 3 parallel AAOS variants (`VAR-A`, `VAR-B`, `VAR-C`), Fleet API, ADB liveness sync | **Complete** | `29/29` passed (`fleet/test_m1_acceptance.py`) |
| **M2 — Vehicle Signal Simulator** | COVESA VSS → AIDL VHAL (`FakeVehicleHardware`), `SC-01..SC-05`, CAN CSV importer | **Complete** | `17/17` passed (`signals/test_m2_acceptance.py`) |
| **M3 — Demo OEM Applications** | Kotlin `APP-1` (Aurelia EV), `APP-2` (Rear-view `< 500 ms`), `APP-3` (Mock Cloud), `v1.0` / `v1.1` / `v1.1-fix` | **Complete** | `17/17` passed (`apps/test_m3_acceptance.py`) |
| **M4 — Staged OTA Rollout** | Eclipse hawkBit 1.0 adapter, 10%→100% rollout, parked+SoC≥30% preconditions, SHA-256 signing, R156 ledger | **Complete** | `17/17` passed (`ota/test_m4_acceptance.py`) |
| **M5 — Equivalence Engine & Gate** | Live ADB runner, Pillow pixel diff, UI/z-order differ, `v1.1` VAR-B BLOCK + `RXSWIN-impact`, `v1.1-fix` PASS | **Complete** | `18/18` passed (`engine/test_m5_acceptance.py`) |
| **M6 — AI Layer (Gemini)** | Release-notes test proposals, human review queue, real M5 failure triage, visual classifier, `ai_records.json` | **Complete** | `ai/test_m6_acceptance.py` |
| **M7 — R156 Dossier & Console** | All 9 UNECE R156 sections from pipeline records, HTML/JSON/PDF export (`< 3 s`), 7-tab React Console | **Complete** | `12/12` passed (`dossier/test_m7_acceptance.py`) |

---

## Fresh Start Quickstart

### 1. Configure Gemini API Key (Optional — Offline Fallback Works Without Key)
Copy `.env.example` to `.env` (already git-ignored) and set `GEMINI_API_KEY`:
```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

### 2. Start Unified Backend API (`:8001`)
```powershell
cd cockpit-ota
pip install -r requirements.txt
python -m uvicorn fleet.manager:app --port 8001 --reload
```

### 3. Start React Operations Console (`:3000`)
```powershell
cd cockpit-ota\console
npm install
npm run dev
```
Open **`http://localhost:3000`** in your browser.

### 4. *(Optional)* Start Real Eclipse hawkBit 1.0 (`:8080`, `admin`/`admin`)
```powershell
docker run -d --name cora-hawkbit -p 8080:8080 hawkbit/hawkbit-update-server:latest
```

---

## Running All Acceptance Suites (M1–M7)

With Fleet Manager running on `:8001`:

```powershell
cd cockpit-ota
python fleet\test_m1_acceptance.py     # M1 — 29 checks (3 live AAOS variants)
python signals\test_m2_acceptance.py   # M2 — 17 checks (VSS->VHAL & replay)
python apps\test_m3_acceptance.py      # M3 — 17 checks (v1.0, v1.1 defect, v1.1-fix, SC-04)
python ota\test_m4_acceptance.py       # M4 — 17 checks (staged OTA, preconditions, tamper, ledger)
python engine\test_m5_acceptance.py    # M5 — 18 checks (live equivalence diff & release gate)
python ai\test_m6_acceptance.py        # M6 — 16 checks (Gemini proposals, review queue, triage)
python dossier\test_m7_acceptance.py   # M7 — 12 checks (9-section R156 JSON/HTML/PDF dossier)
```
