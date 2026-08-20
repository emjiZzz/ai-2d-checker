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

# 3. Set Prototype Flag
$env:VITE_PROTOTYPE_MODE = "true"

$pnpmExe = if (Get-Command pnpm -ErrorAction SilentlyContinue) { "pnpm" } elseif (Test-Path "$env:APPDATA\npm\pnpm.cmd") { "$env:APPDATA\npm\pnpm.cmd" } else { "npx pnpm" }

Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $pnpmExe install

Write-Host "Building React Frontend in PROTOTYPE mode..." -ForegroundColor Yellow
& $pnpmExe --filter desktop build:prototype

Write-Host "Packaging Tauri Desktop Installer (.msi / .exe)..." -ForegroundColor Yellow
& $pnpmExe --filter desktop tauri build

$bundleDir = "$PSScriptRoot\apps\desktop\src-tauri\target\release\bundle"
Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "✅ Prototype Installer Build Complete!" -ForegroundColor Green
Write-Host "Installers are located at:" -ForegroundColor Cyan
Write-Host "  $bundleDir" -ForegroundColor White
Write-Host "=====================================================" -ForegroundColor Green
