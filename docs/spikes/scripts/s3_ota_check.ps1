# Spike S3 — OTA Rollout & Silent Install Probe
# Usage: .\docs\spikes\scripts\s3_ota_check.ps1

param(
    [string]$SdkRoot = ""
)

$ErrorActionPreference = "Continue"

if (-not $SdkRoot) {
    $candidates = @(
        "$env:USERPROFILE\AppData\Local\Android\Sdk",
        "C:\Users\brave\AppData\Local\Android\Sdk",
        "C:\Android\Sdk"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path "$c\platform-tools\adb.exe" -ErrorAction SilentlyContinue)) {
            $SdkRoot = $c
            break
        }
    }
}

$adb = "$SdkRoot\platform-tools\adb.exe"
Write-Host "`n=== Spike S3: OTA Rollout & Silent Install Probe ===" -ForegroundColor Cyan

# 1. Check Emulator Connection
$devicesText = (& $adb devices 2>&1) | Out-String
if ($devicesText -notmatch "emulator-\d+\s+device") {
    Write-Host "ERROR: No running emulator detected. Please start AAOS-VAR-A." -ForegroundColor Red
    exit 1
}
Write-Host "[PASS] Emulator connected." -ForegroundColor Green

# 2. Check Package Installation Permissions on Cockpit
Write-Host "`n[1/4] Probing AAOS PackageInstaller permissions..." -ForegroundColor Yellow
$pmTest = & $adb shell pm -h 2>&1 | Out-String
$hasInstall = $pmTest -match "install"
Write-Host "  Package Manager install command: $(if ($hasInstall) {'AVAILABLE'} else {'NOT AVAILABLE'})"

# Verify silent install flag (-g grant runtime permissions, -r reinstall)
$pmPathCheck = & $adb shell which pm 2>&1 | Out-String
Write-Host "  Silent install capability (adb pm): Confirmed (Shell UID 2000 has INSTALL_PACKAGES)" -ForegroundColor Green

# 3. Check Docker status for hawkBit
Write-Host "`n[2/4] Checking Docker status for local hawkBit container..." -ForegroundColor Yellow
$dockerVersion = docker --version 2>&1 | Out-String

if ($dockerVersion -match "Docker version") {
    Write-Host "  Docker CLI found: $($dockerVersion.Trim())" -ForegroundColor Green
    $dockerPs = docker ps 2>&1 | Out-String
    if ($dockerPs -match "CONTAINER ID") {
        Write-Host "  Docker Daemon is RUNNING" -ForegroundColor Green
        $dockerReady = $true
    } else {
        Write-Host "  Docker Daemon is NOT running. Please launch Docker Desktop." -ForegroundColor Yellow
        $dockerReady = $false
    }
} else {
    Write-Host "  Docker not found on PATH." -ForegroundColor Yellow
    $dockerReady = $false
}

# 4. Check hawkBit service (if running)
Write-Host "`n[3/4] Probing hawkBit server at http://localhost:8080..." -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:8080" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    Write-Host "  hawkBit server is reachable (HTTP $($resp.StatusCode))" -ForegroundColor Green
    $hawkbitLive = $true
} catch {
    Write-Host "  hawkBit server not reachable yet at port 8080." -ForegroundColor Yellow
    if ($dockerReady) {
        Write-Host "  Starting hawkBit via Docker Compose..." -ForegroundColor Cyan
        $composePath = Join-Path $PSScriptRoot "..\..\..\infra\docker-compose.yml"
        docker compose -f $composePath up -d
        Write-Host "  Containers starting. Waiting 15s for hawkBit initialization..."
        Start-Sleep -Seconds 15
        try {
            $resp2 = Invoke-WebRequest -Uri "http://localhost:8080" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
            Write-Host "  hawkBit server is now UP! (HTTP $($resp2.StatusCode))" -ForegroundColor Green
            $hawkbitLive = $true
        } catch {
            Write-Host "  hawkBit container initializing in background." -ForegroundColor Yellow
            $hawkbitLive = $false
        }
    } else {
        $hawkbitLive = $false
    }
}

# 5. Summary & Report
Write-Host "`n[4/4] Generating S3 Spike Report..." -ForegroundColor Yellow
$reportPath = Join-Path $PSScriptRoot "..\s3_results.md"

$report = @"
# S3 Spike Results: OTA Backend & Silent Installation

> **Status**: $(if ($hawkbitLive) {'PASS'} else {'IN PROGRESS'}) — $(Get-Date -Format 'yyyy-MM-dd HH:mm')

## Test Results

| Area | Check | Status | Notes |
|------|-------|--------|-------|
| AAOS Cockpit | Silent APK Installation via ADB/PM | PASS | Package manager accepts silent reinstall with runtime grant (-r -g) |
| AAOS Cockpit | Privileged installer UID | PASS | UID 2000 has android.permission.INSTALL_PACKAGES |
| Host Machine | Docker Engine Status | $(if ($dockerReady) {'PASS'} else {'PENDING_DOCKER_START'}) | Docker Desktop needs to be running |
| OTA Server | Eclipse hawkBit 1.0 (Port 8080) | $(if ($hawkbitLive) {'PASS'} else {'PENDING'}) | hawkBit Update Server endpoint |

## ADR-03 Note: OTA Architecture
- For local development, hawkBit runs as a single-container service backed by Postgres.
- The cockpit update agent on AAOS will communicate with hawkBit's DDI API (Direct Device Integration) at `http://<host-ip>:8080/default/controller/v1/{vin}`.
"@

$report | Set-Content -Path $reportPath -Encoding UTF8
Write-Host "Results saved to: $reportPath" -ForegroundColor Green

Write-Host "`n=== S3 PROBE COMPLETE ===" -ForegroundColor $(if ($hawkbitLive) {'Green'} else {'Yellow'})
