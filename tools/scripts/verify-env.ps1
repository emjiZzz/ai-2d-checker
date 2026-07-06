# ==============================================================================
# AI-2D-Checker — Local Environment Validation & Diagnostics Script
# ==============================================================================
# Run this script to verify dependencies and configurations.
# Execution: powershell -ExecutionPolicy Bypass -File .\tools\scripts\verify-env.ps1
# ==============================================================================

$ErrorActionPreference = "Continue"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "       AI-2D-Checker Verification Diagnostic" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

$allPassed = $true

# Helper to log test status
function Log-Status($testName, $status, $details) {
    if ($status -eq "PASS") {
        Write-Host " [PASS] " -NoNewline -ForegroundColor Green
        Write-Host "$testName : $details" -ForegroundColor White
    } elseif ($status -eq "WARN") {
        Write-Host " [WARN] " -NoNewline -ForegroundColor Yellow
        Write-Host "$testName : $details" -ForegroundColor Yellow
    } else {
        Write-Host " [FAIL] " -NoNewline -ForegroundColor Red
        Write-Host "$testName : $details" -ForegroundColor Red
        $global:allPassed = $false
    }
}

# 1. Check Node.js
if (Get-Command node -ErrorAction SilentlyContinue) {
    $ver = (node -v).Trim()
    Log-Status "Node.js" "PASS" "Found Node.js version $ver"
} else {
    Log-Status "Node.js" "FAIL" "Node.js was not found in environment PATH."
}

# 2. Check pnpm
if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    $ver = (pnpm --version).Trim()
    Log-Status "pnpm" "PASS" "Found pnpm version $ver"
} else {
    Log-Status "pnpm" "FAIL" "pnpm was not found. Install via 'npm install -g pnpm'"
}

# 3. Check Python
if (Get-Command python -ErrorAction SilentlyContinue) {
    $ver = (python --version).Trim()
    Log-Status "Python" "PASS" "Found Python version $ver"
} else {
    Log-Status "Python" "FAIL" "Python was not found in environment PATH."
}

# 4. Check Rust compiler
if (Get-Command rustc -ErrorAction SilentlyContinue) {
    $ver = (rustc --version).Trim()
    Log-Status "Rust Compiler" "PASS" "Found Rust compilation toolchain ($ver)"
} else {
    Log-Status "Rust Compiler" "WARN" "rustc was not found. Required for compiling desktop binaries."
}

# 5. Check local .env exists
if (Test-Path ".env") {
    Log-Status "Env File" "PASS" "Local '.env' config file exists."
    
    # Check for Gemini API key
    $envContent = Get-Content ".env" -Raw
    if ($envContent -match "GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE" -or $envContent -match "GEMINI_API_KEY=\s*$") {
        Log-Status "Gemini API Key" "WARN" "Gemini API Key in '.env' remains unconfigured or placeholder."
    } else {
        Log-Status "Gemini API Key" "PASS" "Gemini API Key value is set."
    }
} else {
    Log-Status "Env File" "FAIL" "No local '.env' file found. Run setup-dev.ps1 to generate."
}

# 6. Check storage directory structure
$storageBase = "storage"
if (Test-Path $storageBase) {
    Log-Status "Storage Root" "PASS" "Local 'storage/' data folder exists."
} else {
    Log-Status "Storage Root" "FAIL" "Local 'storage/' folder does not exist. Run setup-dev.ps1."
}

# 7. Check MongoDB connection health
$mongoHost = "localhost"
$mongoPort = 27017
if ($envContent -match "(?m)^[^#]*MONGO_URI=mongodb://([^:/]+)(?::(\d+))?") {
    $mongoHost = $Matches[1].Trim()
    if ($Matches[2]) {
        $mongoPort = [int]$Matches[2].Trim()
    }
}
try {
    $connection = New-Object System.Net.Sockets.TcpClient($mongoHost, $mongoPort)
    $connection.Close()
    Log-Status "MongoDB Port Check" "PASS" "Successfully connected to MongoDB at ${mongoHost}:${mongoPort}"
} catch {
    Log-Status "MongoDB Port Check" "WARN" "Could not connect to MongoDB on ${mongoHost}:${mongoPort}. Ensure MongoDB Server is started."
}

# 8. Check ODA File Converter path configuration
if ($envContent -match "ODA_CONVERTER_PATH=(.+)") {
    $odaPath = $Matches[1].Trim()
    if (Test-Path $odaPath) {
        Log-Status "ODA File Converter" "PASS" "ODA File Converter found at path: $odaPath"
    } else {
        Log-Status "ODA File Converter" "WARN" "ODA File Converter path configured but file does not exist: $odaPath"
    }
} else {
    Log-Status "ODA File Converter" "FAIL" "ODA_CONVERTER_PATH config variable missing from .env."
}

Write-Host "=====================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host " ✅ Environment Diagnostic Check: ALL PASSED" -ForegroundColor Green
} else {
    Write-Host " ⚠️ Environment Diagnostic Check: HAD WARNINGS/FAILURES" -ForegroundColor Yellow
    Write-Host " Review the failures above and run setup-dev.ps1 to resolve." -ForegroundColor Yellow
}
Write-Host "=====================================================" -ForegroundColor Cyan
