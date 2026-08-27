# ==============================================================================
# Package the backend server for the LAN server PC
# ==============================================================================
#
#     powershell -ExecutionPolicy Bypass -File .\tools\scripts\package-server.ps1
#
# Freezes the backend and leaves a folder that is SAFE TO COPY to
# `C:\Users\Administrator\Desktop\KMTI 2D Checker\`.
#
# ## Why this exists rather than "just run PyInstaller"
#
# The first hand-copied deployment shipped two things it should not have, because they were
# created in the build folder while testing:
#
#   * `.env` -- carrying the Atlas password, and MY machine's settings rather than the server's;
#   * `storage\` -- an entire test data tree, including `secure\.api-token`.
#
# The token was the expensive one. It is encrypted with a MACHINE-BOUND key, so on the server it
# failed to decrypt ("AES decryption error"); and `_restrict_token_file_permissions` chmods it
# 0600, which on Windows sets the READ-ONLY attribute, so the server could not replace it either:
#
#   Failed to encrypt and persist dynamically generated API Token:
#   [Errno 13] Permission denied: ...\storage\secure\.api-token
#
# A build folder that accumulates runtime state is a build folder that ships someone's machine to
# someone else's. This script deletes both every time, so the packaged folder is only ever the
# executable and its runtime.

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $repoRoot "services\backend\.venv\Scripts\python.exe"
$outDir = Join-Path $repoRoot "dist\server\KMTI_2DChecker_Server"

if (-not (Test-Path $python)) { throw "Backend venv not found at $python" }

Write-Host "Freezing backend..." -ForegroundColor Yellow
& $python -m PyInstaller (Join-Path $repoRoot "tools\kmti_2dchecker_server.spec") `
    --noconfirm `
    --distpath (Join-Path $repoRoot "dist\server") `
    --workpath (Join-Path $repoRoot "build\server")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

# Strip anything that is runtime state rather than program. Read-only attributes are cleared
# first: the token file carries one, and Remove-Item refuses it otherwise.
foreach ($leftover in @("storage", ".env")) {
    $path = Join-Path $outDir $leftover
    if (Test-Path $path) {
        Get-ChildItem $path -Recurse -Force -ErrorAction SilentlyContinue |
            ForEach-Object { $_.Attributes = 'Normal' }
        Remove-Item $path -Recurse -Force
        Write-Host "  removed $leftover (runtime state, must not ship)" -ForegroundColor DarkGray
    }
}

# Ship the service files beside the exe. They are what turns a folder of program into something
# that starts itself at logon, so they are part of the package rather than a manual step.
$serviceSrc = Join-Path $PSScriptRoot "server-service"
foreach ($f in @("start-hidden.vbs", "install-service.ps1", "uninstall-service.ps1", ".env.template")) {
    Copy-Item (Join-Path $serviceSrc $f) (Join-Path $outDir $f) -Force
}
Write-Host "  added service scripts + .env.template" -ForegroundColor DarkGray

# Substitute the real Atlas connection string into the shipped template.
#
# The COMMITTED template carries a `__MONGO_URI__` placeholder on purpose -- the connection string
# contains a password, and committing it would put the cluster credential in git history forever.
# It is injected here, at package time, from the build machine's own .env.
#
# 🔴 The result is a real credential inside the installer, on every workstation. Said out loud
# below rather than left for someone to discover.
$repoEnv = Join-Path $repoRoot ".env"
$stagedTemplate = Join-Path $outDir ".env.template"
if (Test-Path $repoEnv) {
    $mongoLine = (Select-String -Path $repoEnv -Pattern '^\s*MONGO_URI\s*=\s*(.+)$' | Select-Object -First 1)
    if ($mongoLine) {
        $uri = $mongoLine.Matches[0].Groups[1].Value.Trim()
        (Get-Content $stagedTemplate -Raw).Replace('__MONGO_URI__', $uri) |
            Set-Content $stagedTemplate -Encoding utf8 -NoNewline
        $host_only = if ($uri -match '@([^/?]+)') { $Matches[1] } else { $uri }
        Write-Host "  MONGO_URI injected -> $host_only" -ForegroundColor DarkGray
        Write-Host "  WARNING: that credential now ships in the installer. Use a scoped Atlas" -ForegroundColor Yellow
        Write-Host "           user (readWrite on ai_2d_checker) before distributing widely." -ForegroundColor Yellow
    } else {
        Write-Host "  WARNING: no MONGO_URI in $repoEnv - template keeps its placeholder and the" -ForegroundColor Yellow
        Write-Host "           sidecar will have no database." -ForegroundColor Yellow
    }
} else {
    Write-Host "  WARNING: no .env at $repoEnv - template keeps its placeholder." -ForegroundColor Yellow
}

$exe = Join-Path $outDir "KMTI_2DChecker_Server.exe"
if (-not (Test-Path $exe)) { throw "Build reported success but $exe is missing." }

# Stage into the Tauri project so `bundle.resources` can pick it up. Tauri resolves resource
# globs relative to tauri.conf.json, and a path climbing out of the project is fragile across CLI
# versions -- so the package is copied IN rather than referenced where it was built.
#
# ⚠ Mirrored, not merged: the staging folder is emptied first. Otherwise a file removed from the
# build (a dependency dropped, a renamed DLL) would linger in the installer forever, and the thing
# shipped would stop matching the thing built.
$stageDir = Join-Path $repoRoot "apps\desktop\src-tauri\server"
if (Test-Path $stageDir) {
    Get-ChildItem $stageDir -Recurse -Force -EA SilentlyContinue | ForEach-Object { $_.Attributes = 'Normal' }
    Remove-Item $stageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null
Copy-Item (Join-Path $outDir "*") $stageDir -Recurse -Force
Write-Host "  staged for bundling: $stageDir" -ForegroundColor DarkGray
$sizeMb = [math]::Round((Get-ChildItem $outDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "Server package ready ($sizeMb MB)" -ForegroundColor Green
Write-Host "  $outDir" -ForegroundColor White
Write-Host ""
Write-Host "Bundled into the desktop installer as a per-workstation sidecar." -ForegroundColor Cyan
Write-Host "Each install runs its own backend on 127.0.0.1 and shares ONE database." -ForegroundColor Cyan
Write-Host ""
Write-Host "  .env.template ships beside the exe; the service installer copies it to .env" -ForegroundColor White
Write-Host "  on first install only, so a per-machine edit survives an upgrade." -ForegroundColor White
Write-Host ""
Write-Host "Do NOT copy a storage\ folder from a build machine -- the API token inside it is" -ForegroundColor Yellow
Write-Host "encrypted per-machine and arrives read-only. Each install creates its own." -ForegroundColor Yellow
Write-Host "=====================================================" -ForegroundColor Green
