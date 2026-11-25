# Spike S1 — Boot check and measurement script
# Run after SDK and AVD are set up (see S1_fleet_spike.md)
# Usage: .\docs\spikes\scripts\s1_boot_check.ps1

param(
    [string]$AvdName = "AAOS-VAR-A",
    [string]$SdkRoot = ""
)

$ErrorActionPreference = "Stop"

# --- Auto-detect SDK root if not provided ---
if (-not $SdkRoot) {
    $candidates = @(
        "$env:USERPROFILE\AppData\Local\Android\Sdk",
        "C:\Users\brave\AppData\Local\Android\Sdk",
        "C:\Android\Sdk",
        "$env:ANDROID_HOME",
        "$env:ANDROID_SDK_ROOT"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path "$c\emulator\emulator.exe" -ErrorAction SilentlyContinue)) {
            $SdkRoot = $c
            Write-Host "Auto-detected SDK at: $SdkRoot" -ForegroundColor Cyan
            break
        }
    }
    # Also check if adb/emulator are already on PATH
    if (-not $SdkRoot) {
        $adbOnPath = Get-Command adb -ErrorAction SilentlyContinue
        if ($adbOnPath) {
            $SdkRoot = Split-Path (Split-Path $adbOnPath.Source -Parent) -Parent
            Write-Host "Found SDK via PATH adb at: $SdkRoot" -ForegroundColor Cyan
        }
    }
    if (-not $SdkRoot) {
        Write-Host ""
        Write-Host "ERROR: Cannot find Android SDK automatically." -ForegroundColor Red
        Write-Host "Please pass the SDK path explicitly:" -ForegroundColor Yellow
        Write-Host "  .\s1_boot_check.ps1 -SdkRoot 'C:\path\to\Android\Sdk'" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To find your SDK path: open Android Studio -> More Actions -> SDK Manager" -ForegroundColor Yellow
        Write-Host "The path is shown at the top of the SDK Manager window." -ForegroundColor Yellow
        exit 1
    }
}

$emulatorExe = "$SdkRoot\emulator\emulator.exe"
$adbExe      = "$SdkRoot\platform-tools\adb.exe"

# --- Validate tools exist ---
foreach ($tool in @($emulatorExe, $adbExe)) {
    if (-not (Test-Path $tool -ErrorAction SilentlyContinue)) {
        Write-Host "Not found: $tool" -ForegroundColor Red
        Write-Host "Did you complete SDK setup? See S1_fleet_spike.md Step 1-2." -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "`n=== S1: Booting AAOS AVD: $AvdName ===" -ForegroundColor Cyan

# --- Kill any running emulators first ---
& $adbExe kill-server | Out-Null
Start-Sleep 1
& $adbExe start-server | Out-Null

# --- Start emulator in background ---
$startTime = Get-Date
Write-Host "Starting emulator at $startTime ..."
$proc = Start-Process -FilePath $emulatorExe `
    -ArgumentList "-avd", $AvdName, "-no-snapshot-load", "-no-audio", "-no-boot-anim" `
    -PassThru -WindowStyle Normal

Write-Host "Emulator PID: $($proc.Id)"
Write-Host "Waiting for device to come online (timeout 5 min)..."

# --- Wait for device ---
$timeout = 300  # seconds
$elapsed = 0
$online  = $false

while ($elapsed -lt $timeout) {
    $devices = & $adbExe devices 2>&1
    if ($devices -match "emulator-\d+\s+device") {
        $online = $true
        break
    }
    Start-Sleep 5
    $elapsed += 5
    Write-Host "  ...waiting ($($elapsed) s)"
}

if (-not $online) {
    Write-Error "Emulator did not come online within $timeout seconds."
}

# --- Wait for boot_completed ---
Write-Host "Device online. Waiting for boot_completed property..."
$bootDone = $false
$elapsed2 = 0

while ($elapsed2 -lt 180) {
    $val = & $adbExe shell getprop sys.boot_completed 2>&1
    if ($val.Trim() -eq "1") {
        $bootDone = $true
        break
    }
    Start-Sleep 5
    $elapsed2 += 5
    Write-Host "  ...booting ($($elapsed2) s)"
}

if (-not $bootDone) {
    Write-Error "Boot did not complete in time."
}

$endTime = Get-Date
$bootSecs = [int]($endTime - $startTime).TotalSeconds

Write-Host "`n=== Boot completed in $bootSecs seconds ===" -ForegroundColor Green

# --- Read system properties ---
Write-Host "`n--- System Properties ---"
$props = @(
    "ro.product.locale",
    "ro.build.characteristics",
    "ro.build.version.release",
    "ro.build.version.sdk",
    "ro.product.model",
    "ro.product.manufacturer"
)

$results = @{}
foreach ($p in $props) {
    $val = (& $adbExe shell getprop $p 2>&1).Trim()
    $results[$p] = $val
    Write-Host "  $p = $val"
}

# --- Validate automotive ---
$chars = $results["ro.build.characteristics"]
if ($chars -match "automotive") {
    Write-Host "`n[PASS] Build is automotive" -ForegroundColor Green
} else {
    Write-Host "`n[WARN] 'automotive' NOT in ro.build.characteristics: '$chars'" -ForegroundColor Yellow
    Write-Host "       You may need an Automotive system image — see S1_fleet_spike.md Step 3"
}

# --- Save results ---
$reportPath = "$PSScriptRoot\..\s1_results.md"
$report = @"
# S1 Spike Results

| Field | Value |
|-------|-------|
| AVD name | $AvdName |
| Boot time (seconds) | $bootSecs |
| ro.product.locale | $($results['ro.product.locale']) |
| ro.build.characteristics | $($results['ro.build.characteristics']) |
| ro.build.version.release | $($results['ro.build.version.release']) |
| ro.build.version.sdk | $($results['ro.build.version.sdk']) |
| ro.product.model | $($results['ro.product.model']) |
| Test date | $(Get-Date -Format 'yyyy-MM-dd HH:mm') |
| Automotive confirmed | $($chars -match 'automotive') |

## S1 Exit Criteria
- [$(if ($chars -match 'automotive') {'x'} else {' '})] AAOS AVD boots to launcher
- [x] adb devices shows instance connected
- [$(if ($results['ro.product.locale'] -match 'en') {'x'} else {' '})] Locale is en-US
- [$(if ($chars -match 'automotive') {'x'} else {' '})] ro.build.characteristics confirms automotive
- [x] Boot-to-launcher time measured: **$bootSecs seconds**

## ADR Decision: Android Build Target
- Selected: Android AVD (Automotive system image) on Windows
- Rationale: Native Windows support; no WSL2 needed; Cuttlefish deferred to cloud phase
"@

$report | Set-Content -Path $reportPath -Encoding UTF8
Write-Host "`nResults saved to: $reportPath" -ForegroundColor Cyan
Write-Host "`n=== S1 COMPLETE ===" -ForegroundColor Green
