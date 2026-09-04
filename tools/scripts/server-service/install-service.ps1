# ==============================================================================
# Register the DraftCheck backend to run in the background, every logon.
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
    [string]$TaskName = "DraftCheck Backend"
)

$ErrorActionPreference = "Stop"

$launcher = Join-Path $ServerDir "start-hidden.vbs"
$exe = Join-Path $ServerDir "DraftCheck_Server.exe"

if (-not (Test-Path $exe)) { throw "Backend executable not found: $exe" }
if (-not (Test-Path $launcher)) { throw "Hidden launcher not found: $launcher" }

# Seed the machine's config from the shipped template, every install.
#
# ## Why the template wins, and why that reverses an earlier decision
#
# This used to seed only when `.env` was absent, to protect a per-machine edit. Measured on a real
# upgrade: Tauri's NSIS installer upgrades IN PLACE and never runs the uninstaller, so `.env` was
# preserved and the installed config could never change. 0.1.6 installed over 0.1.5 and kept
# 0.1.5's database URI; 0.1.7 over 0.1.6 kept it again.
#
# That is fatal to the one operation this deployment actually needs: rotating the Atlas credential
# to a scoped user and pushing it to every workstation. Under the old rule, a new installer would
# reach 21 machines and change nothing, silently.
#
# **The cost, stated rather than hidden: a per-machine edit is overwritten on upgrade.** The
# realistic case is `SIDECAR_PORT` on a machine where 8080 is taken. So the old file is kept as
# `.env.previous`, and any key whose value CHANGED is printed -- an operator who tuned something
# is told, instead of discovering it when the app stops connecting.
$envFile = Join-Path $ServerDir ".env"
$envTemplate = Join-Path $ServerDir ".env.template"

function Get-EnvMap([string]$Path) {
    $map = @{}
    if (Test-Path $Path) {
        foreach ($line in Get-Content $Path) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $map[$Matches[1]] = $Matches[2].Trim() }
        }
    }
    return $map
}

if (Test-Path $envTemplate) {
    $old = Get-EnvMap $envFile
    if (Test-Path $envFile) {
        Copy-Item $envFile "$envFile.previous" -Force
        Remove-Item $envFile -Force
    }
    Copy-Item $envTemplate $envFile -Force
    $new = Get-EnvMap $envFile

    if ($old.Count -gt 0) {
        $changed = @($new.Keys | Where-Object { $old.ContainsKey($_) -and $old[$_] -ne $new[$_] })
        if ($changed.Count -gt 0) {
            Write-Host "  .env reseeded from template; previous saved as .env.previous" -ForegroundColor Yellow
            foreach ($k in $changed) {
                # Never echo a connection string: it carries the database password.
                $redact = if ($k -match 'MONGO|TOKEN|KEY|SECRET') { "<changed>" } else { "$($old[$k]) -> $($new[$k])" }
                Write-Host "    $k : $redact" -ForegroundColor Yellow
            }
            Write-Host "    if you had tuned any of these for this machine, re-apply from .env.previous" -ForegroundColor DarkGray
        } else {
            Write-Host "  .env reseeded from template (no values changed)" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "  created .env from template" -ForegroundColor DarkGray
    }
} else {
    Write-Host "  WARNING: no .env.template - backend will use defaults" -ForegroundColor Yellow
}

Write-Host "Registering background backend..." -ForegroundColor Yellow
Write-Host "  server : $exe" -ForegroundColor DarkGray

# wscript.exe (not cscript) so nothing attaches a console of its own.
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument ('"{0}"' -f $launcher) `
    -WorkingDirectory $ServerDir

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# ExecutionTimeLimit 0 = run forever. The default is 3 days, after which Windows would KILL the
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
    -Description "Runs the DraftCheck backend in the background so the desktop app can be opened and closed freely." | Out-Null

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
