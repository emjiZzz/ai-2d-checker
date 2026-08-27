$ErrorActionPreference = "Stop"

Write-Host "=====================================================" -ForegroundColor Magenta
Write-Host "    AI-2D-Checker Prototype Installer Builder        " -ForegroundColor Magenta
Write-Host "=====================================================" -ForegroundColor Magenta

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
#    Shared with start_desktop.ps1 -- this was ~30 duplicated lines in both, so a toolchain fix
#    landed in whichever script the author happened to run. Dot-sourced, so its $env: writes
#    apply here. Throws if no toolchain resolves, rather than exporting paths that do not exist.
. "$PSScriptRoot\tools\scripts\msvc-env.ps1"

# 3. Set Prototype Flag.
#
# This process variable is the ONLY thing that makes the installer a prototype build. It is not
# a belt-and-braces companion to `--mode prototype`: `tauri.conf.json` sets
# `beforeBuildCommand: "pnpm build"`, so `tauri build` re-runs Vite in production mode and
# overwrites apps/desktop/dist. A `--mode prototype` build performed first is discarded, and only
# an ambient VITE_PROTOTYPE_MODE reaches the bundle that actually ships.
$env:VITE_PROTOTYPE_MODE = "true"

$pnpmExe = if (Get-Command pnpm -ErrorAction SilentlyContinue) { "pnpm" } elseif (Test-Path "$env:APPDATA\npm\pnpm.cmd") { "$env:APPDATA\npm\pnpm.cmd" } else { "npx pnpm" }

Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $pnpmExe install

# The separate `build:prototype` step that used to sit here has been removed rather than fixed.
# It built dist/ and `tauri build` immediately overwrote it, so it cost a full frontend build and
# proved nothing -- while reading like the step that set the mode.
Write-Host "Packaging Tauri Desktop Installer (.msi / .exe)..." -ForegroundColor Yellow
& $pnpmExe --filter desktop tauri build

# 4. Verify what actually shipped, rather than trusting step 3.
#    Reads the stamp `apps/desktop/vite.config.ts` writes at closeBundle. AFTER tauri build,
#    because that is the build whose output goes into the installer.
Write-Host "Verifying build mode..." -ForegroundColor Yellow
& node "$PSScriptRoot\tools\scripts\assert-build-mode.mjs" prototype
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "BUILD ABORTED - the bundle is not a prototype build." -ForegroundColor Red
    Write-Host "Do not distribute the installers in the bundle directory." -ForegroundColor Red
    exit 1
}

# 5. Report where the installers ACTUALLY are.
#
# This printed "$PSScriptRoot\apps\desktop\src-tauri\target\release\bundle" unconditionally, and
# that directory does not exist on this project: `apps/desktop/src-tauri/.cargo/config.toml` sets
#
#     [build]
#     target-dir = "C:/tauri-build-cache"
#
# so cargo -- and therefore the bundler -- writes to C:\tauri-build-cache\release\bundle instead.
# A successful build ended by pointing the operator at an empty path, which is the same shape of
# defect as a checker quoting figures no command can reproduce: the message reads like a fact and
# is derived from nothing.
#
# Resolved in cargo's own precedence order (CARGO_TARGET_DIR beats the config file beats the
# default), then VERIFIED rather than asserted -- if the directory is missing or holds no
# installer, this says so instead of printing a confident path.
$targetDir = $env:CARGO_TARGET_DIR
if ([string]::IsNullOrWhiteSpace($targetDir)) {
    $cargoConfig = "$PSScriptRoot\apps\desktop\src-tauri\.cargo\config.toml"
    if (Test-Path $cargoConfig) {
        $match = Select-String -Path $cargoConfig -Pattern '^\s*target-dir\s*=\s*"(.+?)"' | Select-Object -First 1
        if ($match) { $targetDir = $match.Matches[0].Groups[1].Value }
    }
}
if ([string]::IsNullOrWhiteSpace($targetDir)) {
    $targetDir = "$PSScriptRoot\apps\desktop\src-tauri\target"
}
$bundleDir = Join-Path $targetDir "release\bundle"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "Prototype Installer Build Complete!" -ForegroundColor Green

$installers = @()
if (Test-Path $bundleDir) {
    $installers = Get-ChildItem -Path $bundleDir -Recurse -Include *.msi, *.exe -ErrorAction SilentlyContinue
}

if ($installers.Count -gt 0) {
    Write-Host "Installers:" -ForegroundColor Cyan
    foreach ($installer in $installers) {
        $mb = [math]::Round($installer.Length / 1MB, 1)
        Write-Host "  $($installer.FullName)  ($mb MB)" -ForegroundColor White
    }
} else {
    Write-Host "No installer found under:" -ForegroundColor Red
    Write-Host "  $bundleDir" -ForegroundColor White
    Write-Host "The build reported success, so this is a path resolution problem, not a build" -ForegroundColor Red
    Write-Host "failure -- check [build] target-dir in apps/desktop/src-tauri/.cargo/config.toml." -ForegroundColor Red
}

Write-Host ""
Write-Host "NOTE: this installs the DESKTOP APP ONLY -- it bundles no backend." -ForegroundColor Yellow
Write-Host "      tauri.conf.json declares no externalBin and lib.rs spawns nothing, so on a" -ForegroundColor Yellow
Write-Host "      machine with no FastAPI service running the app opens on 'Connection Lost'." -ForegroundColor Yellow
Write-Host "=====================================================" -ForegroundColor Green
