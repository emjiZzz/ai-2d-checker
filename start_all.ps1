Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "    Starting AI-2D-Checker Platform      " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Start MongoDB database
Write-Host "[1/3] Starting Local MongoDB Database..." -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File .\start-mongo.ps1
Write-Host ""

# 2. Start Backend in a separate window
Write-Host "[2/3] Starting Backend Server (New Window)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -NoExit -File .\services\backend\start.ps1" -WorkingDirectory $PWD
Write-Host "Waiting a few seconds for the backend to initialize..." -ForegroundColor Gray
Start-Sleep -Seconds 5
Write-Host ""

# 3. Start Frontend in the current window
Write-Host "[3/3] Starting Desktop Frontend UI..." -ForegroundColor Yellow
powershell -ExecutionPolicy Bypass -File .\start_desktop.ps1
