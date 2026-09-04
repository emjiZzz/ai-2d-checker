# ==============================================================================
# Remove the background backend: stop the process, unregister the logon task.
# ==============================================================================
#
#     powershell -ExecutionPolicy Bypass -File .\uninstall-service.ps1
#
# Called by the installer's NSIS pre-uninstall hook.
#
# Order matters: stop the process BEFORE removing the task. Unregistering first leaves a
# running backend with nothing to manage it -- it keeps port 8080 bound until the next reboot, so a
# reinstall cannot start its own copy and the user gets an app that talks to an orphaned server
# from the previous version.
#
# Never fatal. An uninstaller that fails leaves the product half-removed, which is worse than
# a stray process. Every step reports what it did and carries on.
#
# Deliberately does NOT delete `storage\`. That folder holds the engineer's uploaded
# drawings and their ground-truth markings. An uninstall -- including the one that happens
# silently as part of an UPGRADE -- must not destroy collected data. Removing it is a manual,
# deliberate act.

[CmdletBinding()]
param([string]$TaskName = "DraftCheck Backend")

$ErrorActionPreference = "Continue"

Write-Host "Removing background backend..." -ForegroundColor Yellow

# 1. Stop the task, if it is running.
try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    if ($task.State -eq "Running") {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Write-Host "  stopped scheduled task" -ForegroundColor DarkGray
    }
} catch {
    Write-Host "  no scheduled task found" -ForegroundColor DarkGray
}

# 2. Kill the server process itself. Stopping the task does not necessarily stop the process it
#    launched -- the task's action was wscript.exe, which exited immediately after spawning the
#    backend, so as far as the scheduler is concerned the action already finished.
$stopped = 0
foreach ($p in (Get-Process -Name "DraftCheck_Server" -ErrorAction SilentlyContinue)) {
    try { Stop-Process -Id $p.Id -Force -ErrorAction Stop; $stopped++ } catch {}
}
if ($stopped -gt 0) { Write-Host "  stopped $stopped backend process(es)" -ForegroundColor DarkGray }

# 3. Unregister, now that nothing is running.
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "  unregistered task: $TaskName" -ForegroundColor Green
} catch {
    Write-Host "  task already absent" -ForegroundColor DarkGray
}

# 4. Remove the generated config.
#
# This is CONFIG, not data, and leaving it is how a wrong setting becomes permanent.
#
# NSIS did not create `.env` -- the post-install hook did -- so the uninstaller has no record of
# it and would leave it behind. `install-service.ps1` then finds it on the next install and
# preserves it, by a rule that exists to protect a per-machine edit. Observed: installing 0.1.6
# over 0.1.5 kept 0.1.5's database URI, the banner reported the old server, and the reinstall
# changed nothing. The fix has to be here, because the install side cannot tell a deliberate edit
# from a stale leftover.
#
# Deliberately narrower than `storage\`, which stays: that holds the engineer's drawings and
# markings, and an UPGRADE runs this uninstaller silently. Config regenerates from the template;
# data does not regenerate from anything.
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    try {
        Copy-Item $envFile "$envFile.previous" -Force
        Remove-Item $envFile -Force
        Write-Host "  removed .env (kept a copy as .env.previous)" -ForegroundColor DarkGray
    } catch {
        Write-Host "  could not remove .env: $_" -ForegroundColor Yellow
    }
}

Write-Host "  storage\ left in place - it holds uploaded drawings and markings." -ForegroundColor Cyan
