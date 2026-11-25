<#
.SYNOPSIS
    Builds and signs all Module 3 Android Automotive OS (AAOS) Kotlin APKs locally:
      - dist/aurelia-ev-v1.0.apk        (APP-1 baseline)
      - dist/aurelia-ev-v1.1.apk        (APP-1 candidate with CHG-101..103 + planted VAR-B portrait defect M3-FR4)
      - dist/aurelia-ev-v1.1-fix.apk    (APP-1 fix keeping CHG-101..103 and removing defect M3-FR5)
      - dist/aurelia-rearview-v1.0.apk  (APP-2 Rear-view stand-in)

.USAGE
    cd "cockpit-ota\apps"
    .\build_apks.ps1
#>

$ErrorActionPreference = "Stop"

$AppsRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir  = Join-Path $AppsRoot "dist"
$BuildTmp = Join-Path $AppsRoot ".build_tmp"

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
New-Item -ItemType Directory -Force -Path $BuildTmp | Out-Null

# ---------------------------------------------------------------------------
# Locate Android SDK, Build Tools & Kotlin Compiler
# ---------------------------------------------------------------------------
$SdkRoot = $env:ANDROID_HOME
if (-not $SdkRoot -or -not (Test-Path $SdkRoot)) {
    $SdkRoot = "$env:LOCALAPPDATA\Android\Sdk"
}
if (-not (Test-Path $SdkRoot)) {
    throw "Android SDK not found at $SdkRoot"
}

$PlatformDir = Join-Path $SdkRoot "platforms\android-34"
if (-not (Test-Path $PlatformDir)) {
    $PlatformDir = Join-Path $SdkRoot "platforms\android-33"
}
$AndroidJar = Join-Path $PlatformDir "android.jar"
$CarJar     = Join-Path $PlatformDir "optional\android.car.jar"

$BuildToolsVersions = Get-ChildItem (Join-Path $SdkRoot "build-tools") | Sort-Object Name -Descending
$BuildTools = $BuildToolsVersions[0].FullName

$Aapt2        = Join-Path $BuildTools "aapt2.exe"
$D8Jar        = Join-Path $BuildTools "lib\d8.jar"
$ZipAlign     = Join-Path $BuildTools "zipalign.exe"
$ApkSignerJar = Join-Path $BuildTools "lib\apksigner.jar"

$KotlincDir      = "C:\Program Files\Android\Android Studio\plugins\Kotlin\kotlinc"
$KotlinCompJar   = Join-Path $KotlincDir "lib\kotlin-compiler.jar"
$KotlinStd       = Join-Path $KotlincDir "lib\kotlin-stdlib.jar"

if (-not (Test-Path $KotlinCompJar)) {
    throw "Kotlin compiler jar not found at $KotlinCompJar. Please install Android Studio or kotlinc."
}

Write-Host "=== CORA Module 3 APK Builder ===" -ForegroundColor Cyan
Write-Host "  SDK Platform : $PlatformDir"
Write-Host "  Build Tools  : $BuildTools"
Write-Host "  Kotlinc JAR  : $KotlinCompJar"

# ---------------------------------------------------------------------------
# Ensure debug signing keystore exists
# ---------------------------------------------------------------------------
$Keystore = Join-Path $DistDir "cora-debug.jks"
if (-not (Test-Path $Keystore)) {
    Write-Host "`n[+] Generating signing keystore: $Keystore" -ForegroundColor Yellow
    & keytool -genkeypair -v `
        -keystore $Keystore `
        -storepass "cora1234" `
        -keypass "cora1234" `
        -alias "cora-release-key" `
        -keyalg RSA -keysize 2048 -validity 3650 `
        -dname "CN=Aurelia Motors POC, OU=CORA, O=Ferfier, L=Munich, C=DE" | Out-Null
}

# ---------------------------------------------------------------------------
# Generic Kotlin AAOS APK build helper
# ---------------------------------------------------------------------------
function Build-AaosApk {
    param(
        [string]$ModuleDir,
        [string]$OutputApkName,
        [int]$VersionCode,
        [string]$VersionName
    )

    Write-Host "`n[+] Building $OutputApkName (v$VersionName / code=$VersionCode)..." -ForegroundColor Green

    $WorkDir = Join-Path $BuildTmp ([System.IO.Path]::GetFileNameWithoutExtension($OutputApkName))
    if (Test-Path $WorkDir) { Remove-Item -Recurse -Force $WorkDir }
    New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

    $ResZip     = Join-Path $WorkDir "res_compiled.zip"
    $GenRDir    = Join-Path $WorkDir "gen_r"
    $ClassesDir = Join-Path $WorkDir "classes"
    $DexDir     = Join-Path $WorkDir "dex"
    $RawApk     = Join-Path $WorkDir "raw.apk"
    $AlignedApk = Join-Path $WorkDir "aligned.apk"
    $FinalApk   = Join-Path $DistDir $OutputApkName

    New-Item -ItemType Directory -Force -Path $GenRDir, $ClassesDir, $DexDir | Out-Null

    $ManifestPath = Join-Path $ModuleDir "AndroidManifest.xml"
    $ResDir       = Join-Path $ModuleDir "src\main\res"
    $KtFiles      = Get-ChildItem -Path (Join-Path $ModuleDir "src\main\kotlin") -Recurse -Filter "*.kt" | ForEach-Object { $_.FullName }

    # 1. Compile resources with aapt2
    & $Aapt2 compile --dir $ResDir -o $ResZip | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "aapt2 compile failed for $OutputApkName" }

    # 2. Link resources & generate R.java
    & $Aapt2 link `
        -I $AndroidJar `
        --manifest $ManifestPath `
        --java $GenRDir `
        --min-sdk-version 30 `
        --target-sdk-version 33 `
        --version-code $VersionCode `
        --version-name $VersionName `
        -o $RawApk `
        $ResZip | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "aapt2 link failed for $OutputApkName" }

    # 3. Compile generated R.java
    $RJavaFiles = Get-ChildItem -Path $GenRDir -Recurse -Filter "R.java" | ForEach-Object { $_.FullName }
    & javac -source 11 -target 11 -cp $AndroidJar -d $ClassesDir $RJavaFiles | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "javac R.java failed for $OutputApkName" }

    # 4. Compile Kotlin sources directly via K2JVMCompiler (avoids cmd.exe '&' path splitting in .bat shims)
    $AppJar = Join-Path $WorkDir "app_kotlin.jar"
    $Classpath = "$AndroidJar;$CarJar;$ClassesDir;$KotlinStd"
    & java -Xmx512m -cp $KotlinCompJar org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib -jvm-target 11 -cp $Classpath -d $AppJar $KtFiles | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "kotlinc failed for $OutputApkName" }

    # 5. Dex bytecode directly via d8.jar (app + R.class + kotlin-stdlib)
    $RClassFiles = Get-ChildItem -Path $ClassesDir -Recurse -Filter "*.class" | ForEach-Object { $_.FullName }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & java -Xmx512m -cp $D8Jar com.android.tools.r8.D8 --min-api 30 --lib $AndroidJar --lib $CarJar --output $DexDir $AppJar $KotlinStd $RClassFiles 2>&1 | Out-Null
    $d8Exit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($d8Exit -ne 0) { throw "d8 failed for $OutputApkName" }

    # 6. Inject classes.dex into APK
    Push-Location $DexDir
    & jar uf $RawApk "classes.dex" | Out-Null
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "jar uf classes.dex failed" }
    Pop-Location

    # 7. Align & Sign APK directly via apksigner.jar
    & $ZipAlign -f 4 $RawApk $AlignedApk | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "zipalign failed for $OutputApkName" }

    & java -Xmx512m -jar $ApkSignerJar sign `
        --ks $Keystore `
        --ks-pass "pass:cora1234" `
        --key-pass "pass:cora1234" `
        --ks-key-alias "cora-release-key" `
        --out $FinalApk `
        $AlignedApk | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "apksigner failed for $OutputApkName" }

    $Hash = (Get-FileHash -Algorithm SHA256 $FinalApk).Hash.ToLower()
    $SizeKB = [Math]::Round((Get-Item $FinalApk).Length / 1KB, 1)
    Write-Host "  [OK] Built $FinalApk ($SizeKB KB, sha256=$($Hash.Substring(0,16))...)" -ForegroundColor Cyan

    return [PSCustomObject]@{
        filename     = $OutputApkName
        version_name = $VersionName
        version_code = $VersionCode
        size_bytes   = (Get-Item $FinalApk).Length
        sha256       = $Hash
    }
}

# Helper to write BuildVariantConfig.kt for APP-1 flavors
function Set-EvVariantConfig {
    param(
        [string]$VersionName,
        [string]$ReleaseTag,
        [bool]$IsV11,
        [bool]$PlantedDefect
    )
    $CfgPath = Join-Path $AppsRoot "app-ev\src\main\kotlin\com\aurelia\ev\BuildVariantConfig.kt"
    $IsV11Str = if ($IsV11) { "true" } else { "false" }
    $DefStr   = if ($PlantedDefect) { "true" } else { "false" }

    $Content = @"
package com.aurelia.ev

object BuildVariantConfig {
    const val VERSION_NAME: String = "$VersionName"
    const val RELEASE_TAG: String = "$ReleaseTag"
    const val IS_V1_1: Boolean = $IsV11Str
    const val PLANTED_DEFECT_PORTRAIT_MODAL: Boolean = $DefStr
}
"@
    Set-Content -Path $CfgPath -Value $Content -Encoding UTF8
}

# ---------------------------------------------------------------------------
# Build all 4 Module 3 APKs
# ---------------------------------------------------------------------------
$ManifestItems = @()

# 1. APP-1 v1.0 (Baseline)
Set-EvVariantConfig -VersionName "1.0.0" -ReleaseTag "v1.0" -IsV11 $false -PlantedDefect $false
$ManifestItems += Build-AaosApk -ModuleDir (Join-Path $AppsRoot "app-ev") -OutputApkName "aurelia-ev-v1.0.apk" -VersionCode 1 -VersionName "1.0.0"

# 2. APP-1 v1.1 (Candidate with declared changes + planted VAR-B portrait defect M3-FR4)
Set-EvVariantConfig -VersionName "1.1.0" -ReleaseTag "v1.1" -IsV11 $true -PlantedDefect $true
$ManifestItems += Build-AaosApk -ModuleDir (Join-Path $AppsRoot "app-ev") -OutputApkName "aurelia-ev-v1.1.apk" -VersionCode 2 -VersionName "1.1.0"

# 3. APP-1 v1.1-fix (Fix build removing only the planted defect M3-FR5)
Set-EvVariantConfig -VersionName "1.1.1-fix" -ReleaseTag "v1.1-fix" -IsV11 $true -PlantedDefect $false
$ManifestItems += Build-AaosApk -ModuleDir (Join-Path $AppsRoot "app-ev") -OutputApkName "aurelia-ev-v1.1-fix.apk" -VersionCode 3 -VersionName "1.1.1-fix"

# Restore default config to v1.0 in working tree
Set-EvVariantConfig -VersionName "1.0.0" -ReleaseTag "v1.0" -IsV11 $false -PlantedDefect $false

# 4. APP-2 Rear-view Stand-in v1.0
$ManifestItems += Build-AaosApk -ModuleDir (Join-Path $AppsRoot "app-rearview") -OutputApkName "aurelia-rearview-v1.0.apk" -VersionCode 1 -VersionName "1.0.0"

# Write SHA-256 artefact manifest (used by M4 OTA & M7 Dossier)
$ManifestJson = @{
    generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    artefacts    = $ManifestItems
} | ConvertTo-Json -Depth 4
Set-Content -Path (Join-Path $DistDir "manifest.json") -Value $ManifestJson -Encoding UTF8

Write-Host "`n=== ALL 4 MODULE 3 APKS BUILT & SIGNED SUCCESSFULLY ===" -ForegroundColor Cyan
Write-Host "Output directory: $DistDir"
