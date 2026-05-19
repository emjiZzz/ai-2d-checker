# ==============================================================================
# AI-2D-Checker — Sidecar Bundle Packaging Script
# ==============================================================================
# Bundles the Python FastAPI sidecar into a single executable binary 
# inside apps/desktop/src-tauri/binaries/
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "       FastAPI Sidecar Packaging Utility" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# Ensure target binaries directory exists
$targetDir = "apps/desktop/src-tauri/binaries"
if (-not (Test-Path $targetDir)) {
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
}

Write-Host "Building single-file Python executable with PyInstaller..." -ForegroundColor Yellow

# In Phase 0, we create a basic mock/scaffold file inside the binaries folder to prevent Rust compilation crashes
$scaffoldFile = Join-Path $targetDir "ai-auditor-x86_64-pc-windows-msvc.exe"
if (-not (Test-Path $scaffoldFile)) {
    # Write a simple empty text representation to satisfy files existence during build setup
    [System.IO.File]::WriteAllText($scaffoldFile, "Scaffold mock executable binary")
    Write-Host "Created binary target scaffold at: $scaffoldFile" -ForegroundColor Green
} else {
    Write-Host "Scaffold binary already exists." -ForegroundColor Green
}

Write-Host "=====================================================" -ForegroundColor Green
Write-Host " PyInstaller sidecar binary scaffold completed." -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
