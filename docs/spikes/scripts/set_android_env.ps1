# PowerShell helper: set ANDROID_HOME, ANDROID_SDK_ROOT, and PATH for the current user
# Run once after Android SDK is downloaded via Android Studio
# Usage: .\docs\spikes\scripts\set_android_env.ps1

$sdkPath = "$env:USERPROFILE\AppData\Local\Android\Sdk"

if (-not (Test-Path $sdkPath)) {
    Write-Error "SDK not found at: $sdkPath`nOpen Android Studio → SDK Manager and download the SDK first."
}

Write-Host "Setting ANDROID_HOME and ANDROID_SDK_ROOT to: $sdkPath"

[System.Environment]::SetEnvironmentVariable("ANDROID_HOME",     $sdkPath, "User")
[System.Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $sdkPath, "User")

$addPaths = @(
    "$sdkPath\platform-tools",
    "$sdkPath\emulator",
    "$sdkPath\tools\bin",
    "$sdkPath\cmdline-tools\latest\bin"
)

$currentPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")

foreach ($p in $addPaths) {
    if ($currentPath -notlike "*$p*") {
        $currentPath = "$currentPath;$p"
        Write-Host "  Added to PATH: $p"
    } else {
        Write-Host "  Already in PATH: $p"
    }
}

[System.Environment]::SetEnvironmentVariable("PATH", $currentPath, "User")

Write-Host "`nDone. RESTART your terminal, then verify with:"
Write-Host "  adb --version"
Write-Host "  emulator -version"
