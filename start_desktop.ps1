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

# 2. Setup MSVC Environment (link.exe, cl.exe, Windows SDK).
. "$PSScriptRoot\tools\scripts\msvc-env.ps1"
Write-Host ""

if (-not $isProdTarget) {
    # Ensure local MongoDB and Backend are running
    Write-Host "Checking local services status..." -ForegroundColor Yellow
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
        Write-Host "✅ Local Backend is already running on port $port." -ForegroundColor Green
    }
} else {
    Write-Host "Connected to cloud backend. Skipping local Mongo & FastAPI startup." -ForegroundColor Green
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
