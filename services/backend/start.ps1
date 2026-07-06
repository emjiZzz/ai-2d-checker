# ==============================================================================
# AI-2D-Checker — Standalone Backend Launch Utility
# ==============================================================================
# Launches the FastAPI backend service locally on port 8080.
# Execution: powershell -ExecutionPolicy Bypass -File .\services\backend\start.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "      AI-2D-Checker FastAPI Standalone Launcher" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# Ensure venv exists or prompt to install
$venvDir = Join-Path $PSScriptRoot ".venv"

if (-not (Test-Path $venvDir)) {
    Write-Host "⚠️ Python Virtual Environment (.venv) not found. Initializing..." -ForegroundColor Yellow
    python -m venv $venvDir
    Write-Host "✅ Virtual environment created at $venvDir" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "Activating Python Virtual Environment..." -ForegroundColor Yellow
$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"
& $activateScript

# Install / update requirements
Write-Host "Verifying backend dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r (Join-Path $PSScriptRoot "requirements.txt")

# Determine port from Env or default
$envFile = Join-Path $PSScriptRoot "..\..\.env"
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

Write-Host "`n🚀 Booting FastAPI Backend Service..." -ForegroundColor Green
Write-Host "   URL: http://127.0.0.1:$port" -ForegroundColor Green
Write-Host "   Docs: http://127.0.0.1:$port/docs" -ForegroundColor Green
Write-Host "   Press Ctrl+C to terminate backend process.`n" -ForegroundColor DarkCyan

# Launch Uvicorn with PYTHONPATH configured for local imports
$workspaceRoot = Resolve-Path "$PSScriptRoot\..\.."
$env:PYTHONPATH = "$workspaceRoot;$PSScriptRoot;$env:PYTHONPATH"
python -m uvicorn services.backend.main:app --host 127.0.0.1 --port $port --reload --reload-dir "$PSScriptRoot"
