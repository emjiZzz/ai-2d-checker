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
    py -m venv $venvDir
    Write-Host "✅ Virtual environment created at $venvDir" -ForegroundColor Green
}

# Activate virtual environment.
#
# DOT-SOURCED (`.`), not called (`&`). Activate.ps1 works by mutating $env:PATH and $env:VIRTUAL_ENV
# in the *current* scope; the call operator runs it in a child scope that exits immediately, so the
# activation evaporated before it could affect anything below. This script therefore looked
# activated and never was, and the bare `python` further down resolved to whatever was first on
# PATH — the system interpreter.
#
# That is not cosmetic. The system interpreter here has NEITHER `xlrd` NOR `pypdf`, so a backend
# started by this script could not ingest .xls or PDF standards, and ran older FastAPI/uvicorn
# than requirements.txt pins. `.claude/launch.json` had it right all along, which is why the two
# launch paths behaved differently.
Write-Host "Activating Python Virtual Environment..." -ForegroundColor Yellow
$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"
. $activateScript

# Verify backend dependencies
# Write-Host "Verifying backend dependencies..." -ForegroundColor Yellow
# python -m pip install --upgrade pip
# pip install -r (Join-Path $PSScriptRoot "requirements.txt")

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
# Invoked by absolute path rather than as bare `python`, so the interpreter is correct even if
# activation is bypassed, shadowed, or silently fails the way it did above. Belt and braces: the
# consequence of getting this wrong is not a crash but a backend that runs and is quietly missing
# two file-format parsers.
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "❌ venv interpreter not found at $venvPython" -ForegroundColor Red
    Write-Host "   Create it with:  py -m venv `"$venvDir`"" -ForegroundColor Yellow
    exit 1
}
Write-Host "   Interpreter: $venvPython" -ForegroundColor DarkGray
& $venvPython -m uvicorn services.backend.main:app --host 127.0.0.1 --port $port --reload --reload-dir "$PSScriptRoot"
