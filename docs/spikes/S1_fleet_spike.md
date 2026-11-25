# Spike S1 — AAOS Emulator Boot on Windows

## Question
Can an Android Automotive OS (AAOS) AVD boot locally on Windows, be reachable via `adb`, and display a live screen?

## Exit Criteria
- [ ] AAOS AVD boots to launcher
- [ ] `adb devices` shows the instance connected
- [ ] `adb shell getprop ro.product.locale` returns `en-US`
- [ ] `adb shell getprop ro.build.characteristics` confirms `automotive`
- [ ] Boot-to-launcher time measured and recorded
- [ ] Screen visible (Android Studio emulator window or scrcpy)

## Status: IN PROGRESS

---

## Setup Steps (follow in order)

### Step 1 — SDK Download via Android Studio

1. Open **Android Studio** (`C:\Program Files\Android\Android Studio\bin\studio64.exe`)
2. Go to **More Actions → SDK Manager** (or Tools → SDK Manager)
3. Under **SDK Platforms** tab, check:
   - `Android 15 (API 35)` — Automotive (or Android 14 / API 34 if 15 not available)
4. Under **SDK Tools** tab, check:
   - Android SDK Build-Tools (latest)
   - Android Emulator
   - Android SDK Platform-Tools
   - Intel x86 Emulator Accelerator (HAXM) **or** Android Emulator Hypervisor Driver (AEHD)
5. Click **Apply → OK** — downloads ~3–4 GB

### Step 2 — Set Environment Variables

After SDK downloads (default path: `C:\Users\JatinChhabra\AppData\Local\Android\Sdk`):

```powershell
# Run in PowerShell as Administrator
[System.Environment]::SetEnvironmentVariable("ANDROID_HOME", "C:\Users\JatinChhabra\AppData\Local\Android\Sdk", "User")
[System.Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", "C:\Users\JatinChhabra\AppData\Local\Android\Sdk", "User")

$path = [System.Environment]::GetEnvironmentVariable("PATH", "User")
$additions = "C:\Users\JatinChhabra\AppData\Local\Android\Sdk\platform-tools;C:\Users\JatinChhabra\AppData\Local\Android\Sdk\emulator;C:\Users\JatinChhabra\AppData\Local\Android\Sdk\tools\bin"
[System.Environment]::SetEnvironmentVariable("PATH", "$path;$additions", "User")
```

Then **restart your terminal** and verify:
```powershell
adb --version
emulator -version
```

### Step 3 — Create AAOS AVD

1. In Android Studio → **More Actions → Virtual Device Manager** (or Tools → Device Manager)
2. Click **Create Device**
3. Under **Category** select **Automotive**
4. Pick **Automotive (1024p landscape)** hardware profile
5. Click **Next** → Select system image:
   - Tab: **Other Images**
   - Look for: `Android Automotive with Google APIs` (API 33 or 34)
   - Download if not present (click the download arrow)
6. Click **Next** → Name: `AAOS-VAR-A` → Finish

### Step 4 — Boot and Verify

Boot via CLI (run from project root after S1 setup script):
```powershell
# See scripts/s1_boot_check.ps1 in this folder
.\docs\spikes\scripts\s1_boot_check.ps1
```

Or manually:
```powershell
emulator -avd AAOS-VAR-A -no-snapshot-load
# Wait ~2–3 min for first boot
adb wait-for-device
adb shell getprop ro.product.locale
adb shell getprop ro.build.characteristics
adb shell getprop ro.build.version.release
```

### Step 5 — Record Results

Fill in `s1_results.md` in this folder.

---

## Notes / Decisions
- Android Studio installed at: `C:\Program Files\Android\Android Studio`
- SDK will be downloaded to: `C:\Users\JatinChhabra\AppData\Local\Android\Sdk`
- Using AVD (Android Virtual Device) instead of Cuttlefish — AVD runs natively on Windows; Cuttlefish needs Linux/WSL2
- HAXM or AEHD required for hardware acceleration; AEHD preferred on modern Windows (doesn't need VT-x in BIOS separately)
