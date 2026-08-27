$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Magenta
Write-Host "    AI-2D-Checker Prototype Installer Builder        " -ForegroundColor Magenta
Write-Host "=====================================================" -ForegroundColor Magenta

# 1. Inject Rust Cargo Path
$cargoPath = "$env:USERPROFILE\.cargo\bin"
if ($env:Path -notmatch [regex]::Escape($cargoPath)) {
    $env:Path += ";$cargoPath"
}

# 1.5 Inject Node.js & pnpm Path
$nodePath = "C:\Program Files\nodejs"
$npmGlobalPath = "$env:APPDATA\npm"
if ($env:Path -notmatch [regex]::Escape($npmGlobalPath)) {
    $env:Path = "$npmGlobalPath;$env:Path"
}
if (Test-Path $nodePath) {
    if ($env:Path -notmatch [regex]::Escape($nodePath)) {
        $env:Path = "$nodePath;$env:Path"
    }
}

# 2. Setup Portable MSVC Environment (link.exe, cl.exe, Windows SDK)
$msvcRoot = if (Test-Path "$PSScriptRoot\msvc\VC\Tools\MSVC") { "$PSScriptRoot\msvc" } else { "$env:USERPROFILE\msvc" }
$msvcVerFolder = Get-ChildItem "$msvcRoot\VC\Tools\MSVC" -ErrorAction SilentlyContinue | Select-Object -First 1
$msvcVer = if ($msvcVerFolder) { $msvcVerFolder.Name } else { "14.51.36231" }

$sdkRoot = if (Test-Path "$msvcRoot\Windows Kits\10") { "$msvcRoot\Windows Kits\10" } else { "C:\Program Files (x86)\Windows Kits\10" }
$sdkVerFolder = Get-ChildItem "$sdkRoot\bin" -Filter "10.*" -ErrorAction SilentlyContinue | Select-Object -First 1
$sdkVer = if ($sdkVerFolder) { $sdkVerFolder.Name } else { "10.0.26100.0" }

$msvcBin = "$msvcRoot\VC\Tools\MSVC\$msvcVer\bin\Hostx64\x64"
$sdkBin = "$sdkRoot\bin\$sdkVer\x64"

$env:Path = "$msvcBin;$sdkBin;$env:Path"

$env:INCLUDE = @(
    "$msvcRoot\VC\Tools\MSVC\$msvcVer\include",
    "$sdkRoot\Include\$sdkVer\ucrt",
    "$sdkRoot\Include\$sdkVer\shared",
    "$sdkRoot\Include\$sdkVer\um",
    "$sdkRoot\Include\$sdkVer\winrt",
    "$sdkRoot\Include\$sdkVer\cppwinrt"
) -join ";"

$env:LIB = @(
    "$msvcRoot\VC\Tools\MSVC\$msvcVer\lib\x64",
    "$sdkRoot\Lib\$sdkVer\ucrt\x64",
    "$sdkRoot\Lib\$sdkVer\um\x64"
) -join ";"

Write-Host "✅ MSVC Environment injected." -ForegroundColor Green

# 3. Set Prototype Flag.
#
# This process variable is the ONLY thing that makes the installer a prototype build. It is not
# a belt-and-braces companion to `--mode prototype`: `tauri.conf.json` sets
# `beforeBuildCommand: "pnpm build"`, so `tauri build` re-runs Vite in production mode and
# overwrites apps/desktop/dist. A `--mode prototype` build performed first is discarded, and only
# an ambient VITE_PROTOTYPE_MODE reaches the bundle that actually ships.
$env:VITE_PROTOTYPE_MODE = "true"

$pnpmExe = if (Get-Command pnpm -ErrorAction SilentlyContinue) { "pnpm" } elseif (Test-Path "$env:APPDATA\npm\pnpm.cmd") { "$env:APPDATA\npm\pnpm.cmd" } else { "npx pnpm" }

Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $pnpmExe install

# The separate `build:prototype` step that used to sit here has been removed rather than fixed.
# It built dist/ and `tauri build` immediately overwrote it, so it cost a full frontend build and
# proved nothing -- while reading like the step that set the mode.
Write-Host "Packaging Tauri Desktop Installer (.msi / .exe)..." -ForegroundColor Yellow
& $pnpmExe --filter desktop tauri build

# 4. Verify what actually shipped, rather than trusting step 3.
#    Reads the stamp `apps/desktop/vite.config.ts` writes at closeBundle. AFTER tauri build,
#    because that is the build whose output goes into the installer.
Write-Host "Verifying build mode..." -ForegroundColor Yellow
& node "$PSScriptRoot\tools\scripts\assert-build-mode.mjs" prototype
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "BUILD ABORTED - the bundle is not a prototype build." -ForegroundColor Red
    Write-Host "Do not distribute the installers in the bundle directory." -ForegroundColor Red
    exit 1
}

$bundleDir = "$PSScriptRoot\apps\desktop\src-tauri\target\release\bundle"
Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "✅ Prototype Installer Build Complete!" -ForegroundColor Green
Write-Host "Installers are located at:" -ForegroundColor Cyan
Write-Host "  $bundleDir" -ForegroundColor White
Write-Host "=====================================================" -ForegroundColor Green
