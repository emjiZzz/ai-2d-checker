# ==============================================================================
# Register the KMTI 2D Checker backend to run in the background, every logon.
# ==============================================================================
#
#     powershell -ExecutionPolicy Bypass -File .\install-service.ps1 [-ServerDir <path>]
#
# Called by the installer's NSIS post-install hook, and runnable by hand for repair.
#
# ## Why a Scheduled Task and not a Windows Service
#
# A Windows Service needs administrator rights to register, and the whole point of this rollout is
# that an engineer installs the app and never thinks about a backend again. A per-user logon task
# needs no elevation, survives the app being closed and reopened, restarts at every logon, and is
# removed cleanly on uninstall.
#
# The trade-off, stated plainly: the backend runs only while that user is LOGGED IN. It is not
# available before logon or to other users on the same machine. For a per-installation sidecar
# serving one engineer's desktop app, that is exactly the required lifetime -- and it avoids
# storing credentials, which "run whether user is logged on or not" would demand.
#
# ## Idempotent on purpose
#
# Re-running replaces the task rather than erroring, so a repair install and an upgrade both work
# without an uninstall first.

[CmdletBinding()]
param(
    # Defaults to the folder holding this script, which is where the installer puts everything.
    [string]$ServerDir = $PSScriptRoot,
    [string]$TaskName = "KMTI 2D Checker Backend"
)

$ErrorActionPreference = "Stop"

$launcher = Join-Path $ServerDir "start-hidden.vbs"
$exe = Join-Path $ServerDir "KMTI_2DChecker_Server.exe"

if (-not (Test-Path $exe)) { throw "Backend executable not found: $exe" }
if (-not (Test-Path $launcher)) { throw "Hidden launcher not found: $launcher" }

# Seed the machine's config on FIRST install only.
#
# ⚠ Never overwrite an existing .env. An upgrade reruns this, and clobbering the file would undo
# any per-machine change -- a different SIDECAR_PORT where 8080 was taken, a corrected MONGO_URI --
# silently, and the symptom would appear as "the app stopped working after the update".
$envFile = Join-Path $ServerDir ".env"
$envTemplate = Join-Path $ServerDir ".env.template"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envTemplate) {
        Copy-Item $envTemplate $envFile
        Write-Host "  created .env from template" -ForegroundColor DarkGray
    } else {
        Write-Host "  WARNING: no .env and no .env.template - backend will use defaults" -ForegroundColor Yellow
    }
} else {
    # Say WHICH database it kept. "left untouched" alone is what let a stale URI survive a
    # reinstall unnoticed -- the message was true and told the operator nothing actionable.
    $keptUri = (Select-String -Path $envFile -Pattern '^\s*MONGO_URI\s*=\s*(.+)$' | Select-Object -First 1)
    $keptHost = if ($keptUri -and $keptUri.Matches[0].Groups[1].Value -match '@([^/?]+)') { $Matches[1] }
                elseif ($keptUri) { $keptUri.Matches[0].Groups[1].Value } else { "unset" }
    Write-Host "  .env already present - left untouched (database: $keptHost)" -ForegroundColor Yellow
    Write-Host "    delete it and re-run this script to reseed from .env.template" -ForegroundColor DarkGray
}

Write-Host "Registering background backend..." -ForegroundColor Yellow
Write-Host "  server : $exe" -ForegroundColor DarkGray

# wscript.exe (not cscript) so nothing attaches a console of its own.
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument ('"{0}"' -f $launcher) `
    -WorkingDirectory $ServerDir

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# ⚠ ExecutionTimeLimit 0 = run forever. The default is 3 days, after which Windows would KILL the
# backend and the app would start reporting "Connection Lost" for no visible reason on any machine
# left logged in over a long weekend.
#
# RestartCount/RestartInterval cover a crash: the app polls /health every 5s and recovers on its
# own once the backend is back, so an automatic restart is invisible rather than disruptive.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Interactive: runs as the logged-in user, in their session, with their environment and their
# %LOCALAPPDATA% -- which is where the API token is published for the desktop client to read.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop; Write-Host "  replaced existing task" -ForegroundColor DarkGray } catch {}

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Runs the KMTI 2D Checker backend in the background so the desktop app can be opened and closed freely." | Out-Null

Write-Host "  task registered: $TaskName" -ForegroundColor Green

# Start it now, so the user does not have to log out and back in after installing. Skipped when
# something is already listening -- a second instance would fail to bind and add a confusing
# error to the log for no reason.
$busy = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "  port 8080 already in use - not starting a second instance" -ForegroundColor Yellow
} else {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "  started" -ForegroundColor Green
}

Write-Host ""
Write-Host "The backend now starts automatically at logon and keeps running when the app closes." -ForegroundColor Cyan
Write-Host "First start takes up to a minute; the app shows 'Connection Lost' until it is ready." -ForegroundColor DarkGray
