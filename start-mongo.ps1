# ==============================================================================
# start-mongo.ps1 — Starts MongoDB without requiring Windows Service / admin rights
# Uses the successfully installed MongoDB v7.0 executable to avoid AVX issues.
# ==============================================================================

$mongod = "$env:USERPROFILE\mongodb\mongodb-win32-x86_64-windows-7.0.12\bin\mongod.exe"
$dataDir   = "$PSScriptRoot\storage\mongodb_data"
$logFile   = "$PSScriptRoot\storage\mongodb_data\mongod.log"
$port      = 27017

# Ensure data directory exists
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "         AI-2D-Checker — MongoDB Launcher            " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Data dir : $dataDir" -ForegroundColor Gray
Write-Host "  Log file : $logFile" -ForegroundColor Gray
Write-Host "  Port     : $port" -ForegroundColor Gray
Write-Host ""

# Check if MongoDB is already running on port 27017
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "✅ MongoDB is already running on port $port — nothing to do." -ForegroundColor Green
    exit 0
}

Write-Host "Starting MongoDB 7.0 (standalone, no service required)..." -ForegroundColor Yellow
Start-Process -FilePath $mongod `
    -ArgumentList "--dbpath `"$dataDir`" --port $port --logpath `"$logFile`" --logappend --bind_ip 127.0.0.1" `
    -WindowStyle Hidden

# Wait up to 15 seconds for MongoDB to be reachable
$attempts = 0
do {
    Start-Sleep -Seconds 1
    $attempts++
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
} while (-not $conn -and $attempts -lt 15)

if ($conn) {
    Write-Host "✅ MongoDB started successfully on port $port" -ForegroundColor Green
} else {
    Write-Host "❌ MongoDB failed to start. Check log at: $logFile" -ForegroundColor Red
    exit 1
}
