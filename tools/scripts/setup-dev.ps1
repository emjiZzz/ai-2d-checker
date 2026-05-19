# ==============================================================================
# AI-2D-Checker — Local Developer Environment Setup Script
# ==============================================================================
# Run this script to bootstrap your local workspace.
# Execution: powershell -ExecutionPolicy Bypass -File .\tools\scripts\setup-dev.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "         AI-2D-Checker Dev Environment Bootstrap" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# 1. Check Node.js Version
Write-Host "`n[1/7] Checking Node.js installation..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    Write-Host "     Found Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "     ❌ Error: Node.js is not installed. Please install Node.js >= 20.0.0." -ForegroundColor Red
    Exit 1
}

# 2. Check pnpm Version
Write-Host "`n[2/7] Checking pnpm package manager..." -ForegroundColor Yellow
try {
    $pnpmVersion = pnpm --version
    Write-Host "     Found pnpm: $pnpmVersion" -ForegroundColor Green
} catch {
    Write-Host "     ⚠️ pnpm is not installed. Attempting to install pnpm globally..." -ForegroundColor DarkYellow
    try {
        npm install -g pnpm
        $pnpmVersion = pnpm --version
        Write-Host "     Successfully installed pnpm: $pnpmVersion" -ForegroundColor Green
    } catch {
        Write-Host "     ❌ Error: Failed to install pnpm. Please install it manually with 'npm i -g pnpm'." -ForegroundColor Red
        Exit 1
    }
}

# 3. Check Python Installation
Write-Host "`n[3/7] Checking Python 3.12+ installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version
    Write-Host "     Found Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "     ❌ Error: Python is not installed. Please install Python >= 3.12." -ForegroundColor Red
    Exit 1
}

# 4. Check Rust Installation
Write-Host "`n[4/7] Checking Rust compiler (rustc)..." -ForegroundColor Yellow
try {
    $rustcVersion = rustc --version
    Write-Host "     Found Rust: $rustcVersion" -ForegroundColor Green
} catch {
    Write-Host "     ⚠️ Rust compiler (rustc) was not found." -ForegroundColor DarkYellow
    Write-Host "     Please install Rustup and the MSVC compiler tools from https://rustup.rs/." -ForegroundColor DarkYellow
}

# 5. Create storage/ Directory Hierarchy
Write-Host "`n[5/7] Initializing git-ignored local storage directories..." -ForegroundColor Yellow
$storageDirs = @(
    "storage/drawings/originals",
    "storage/drawings/converted",
    "storage/processed/rasterized",
    "storage/processed/vectors",
    "storage/processed/normalized",
    "storage/comparisons/overlays",
    "storage/comparisons/metadata",
    "storage/reports/generated",
    "storage/reports/drafts",
    "storage/ai-artifacts/embeddings",
    "storage/ai-artifacts/prompts",
    "storage/ai-artifacts/responses",
    "storage/standards/library",
    "storage/cache/thumbnails",
    "storage/cache/temp",
    "storage/db",
    "storage/logs/app",
    "storage/logs/audit-trail",
    "storage/logs/sidecar",
    "storage/secure/encrypted-config"
)

foreach ($dir in $storageDirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Write-Host "     Created: $dir" -ForegroundColor DarkGray
    }
}
Write-Host "     ✅ Storage directory structure successfully initialized." -ForegroundColor Green

# 6. Initialize Environment File
Write-Host "`n[6/7] Creating environment configurations..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "     ✅ Created local '.env' from '.env.example'. Please update your Gemini API key." -ForegroundColor Green
} else {
    Write-Host "     Found existing '.env' file. Skipping copy." -ForegroundColor Green
}

# 7. Install Monorepo Package Dependencies
Write-Host "`n[7/7] Installing Node.js workspace dependencies..." -ForegroundColor Yellow
try {
    pnpm install
    Write-Host "     ✅ Workspace node dependencies installed." -ForegroundColor Green
} catch {
    Write-Host "     ❌ Error: Failed to run 'pnpm install'." -ForegroundColor Red
    Exit 1
}

Write-Host "`n=====================================================" -ForegroundColor Green
Write-Host " 🎉 Setup completed successfully!" -ForegroundColor Green
Write-Host " Run 'pnpm verify' to run the verification checklist." -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
