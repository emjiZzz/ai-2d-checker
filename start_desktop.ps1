$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "      AI-2D-Checker Tauri Desktop Launcher      " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# 1. Inject Rust Cargo Path
$cargoPath = "$env:USERPROFILE\.cargo\bin"
if ($env:Path -notmatch [regex]::Escape($cargoPath)) {
    $env:Path += ";$cargoPath"
}

# 1.5 Inject Node.js Path
$nodePath = "C:\Program Files\nodejs"
if (Test-Path $nodePath) {
    if ($env:Path -notmatch [regex]::Escape($nodePath)) {
        $env:Path = "$nodePath;$env:Path"
    }
}

# 2. Setup Portable MSVC Environment (link.exe, cl.exe, Windows SDK)
$msvcRoot = "$env:USERPROFILE\msvc"
$msvcVer = "14.51.36231"
$sdkVer = "10.0.28000.0"

$msvcBin = "$msvcRoot\VC\Tools\MSVC\$msvcVer\bin\Hostx64\x64"
$sdkBin = "$msvcRoot\Windows Kits\10\bin\$sdkVer\x64"

# Add MSVC and SDK binaries to PATH
$env:Path = "$msvcBin;$sdkBin;$env:Path"

# Set INCLUDE paths for the compiler
$env:INCLUDE = @(
    "$msvcRoot\VC\Tools\MSVC\$msvcVer\include",
    "$msvcRoot\Windows Kits\10\Include\$sdkVer\ucrt",
    "$msvcRoot\Windows Kits\10\Include\$sdkVer\shared",
    "$msvcRoot\Windows Kits\10\Include\$sdkVer\um",
    "$msvcRoot\Windows Kits\10\Include\$sdkVer\winrt",
    "$msvcRoot\Windows Kits\10\Include\$sdkVer\cppwinrt"
) -join ";"

# Set LIB paths for the linker
$env:LIB = @(
    "$msvcRoot\VC\Tools\MSVC\$msvcVer\lib\x64",
    "$msvcRoot\Windows Kits\10\Lib\$sdkVer\ucrt\x64",
    "$msvcRoot\Windows Kits\10\Lib\$sdkVer\um\x64"
) -join ";"

Write-Host "MSVC link.exe and Windows SDK injected successfully." -ForegroundColor Green
Write-Host "Starting Tauri Desktop Dev Server..." -ForegroundColor Green
Write-Host ""

# 3. Install packages
Write-Host "Installing packages..." -ForegroundColor Yellow
npx pnpm install

# 4. Launch Tauri
npx pnpm --filter desktop tauri dev
