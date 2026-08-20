param(
    [switch]$Prototype
)

$ErrorActionPreference = "Stop"

$modeLabel = if ($Prototype) { "PROTOTYPE (2D Workspace Only)" } else { "FULL DEVELOPMENT" }

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "      AI-2D-Checker Tauri Desktop Launcher           " -ForegroundColor Cyan
Write-Host "      Mode: $modeLabel                               " -ForegroundColor $(if ($Prototype) { "Magenta" } else { "Green" })
Write-Host "=====================================================" -ForegroundColor Cyan

if ($Prototype) {
    $env:VITE_PROTOTYPE_MODE = "true"
} else {
    $env:VITE_PROTOTYPE_MODE = "false"
}

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

# Add MSVC and SDK binaries to PATH
$env:Path = "$msvcBin;$sdkBin;$env:Path"

# Set INCLUDE paths for the compiler
$env:INCLUDE = @(
    "$msvcRoot\VC\Tools\MSVC\$msvcVer\include",
    "$sdkRoot\Include\$sdkVer\ucrt",
    "$sdkRoot\Include\$sdkVer\shared",
    "$sdkRoot\Include\$sdkVer\um",
    "$sdkRoot\Include\$sdkVer\winrt",
    "$sdkRoot\Include\$sdkVer\cppwinrt"
) -join ";"

# Set LIB paths for the linker
$env:LIB = @(
    "$msvcRoot\VC\Tools\MSVC\$msvcVer\lib\x64",
    "$sdkRoot\Lib\$sdkVer\ucrt\x64",
    "$sdkRoot\Lib\$sdkVer\um\x64"
) -join ";"

Write-Host "MSVC link.exe and Windows SDK injected successfully." -ForegroundColor Green
Write-Host ""

# Ensure MongoDB and Backend are running
Write-Host "Checking services status..." -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File .\start-mongo.ps1

# Determine port from Env or default
$envFile = ".\.env"
$port = 8080
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
    if ($envContent -match "SIDECAR_PORT=(\d+)") {
        $foundPort = [int]$Matches[1]
        if ($foundPort -ne 0) {
            $port = $foundPort
        }
    }
}

$backendRunning = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if (-not $backendRunning) {
    Write-Host "Backend is not running on port $port. Launching FastAPI Backend Service..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -NoExit -File .\services\backend\start.ps1" -WorkingDirectory $PWD
    Write-Host "Waiting a few seconds for backend to initialize..." -ForegroundColor Gray
    Start-Sleep -Seconds 5
}
else {
    Write-Host "✅ Backend is already running on port $port." -ForegroundColor Green
}

# Free port 1420 if previously occupied by background vite process
$vitePortConn = Get-NetTCPConnection -LocalPort 1420 -State Listen -ErrorAction SilentlyContinue
if ($vitePortConn) {
    Write-Host "Freeing occupied port 1420..." -ForegroundColor Yellow
    Stop-Process -Id $vitePortConn.OwningProcess -Force -ErrorAction SilentlyContinue
}

Write-Host "Starting Tauri Desktop Dev Server..." -ForegroundColor Green
Write-Host ""

$pnpmExe = if (Get-Command pnpm -ErrorAction SilentlyContinue) { "pnpm" } elseif (Test-Path "$env:APPDATA\npm\pnpm.cmd") { "$env:APPDATA\npm\pnpm.cmd" } else { "npx pnpm" }

# 3. Install packages
Write-Host "Installing packages..." -ForegroundColor Yellow
& $pnpmExe install

# 4. Launch Tauri
& $pnpmExe --filter desktop tauri dev
