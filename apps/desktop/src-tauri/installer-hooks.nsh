; ============================================================================
; NSIS hooks - register / remove the background backend
; ============================================================================
;
; Wired in via `bundle.windows.nsis.installerHooks` in tauri.conf.json.
;
; The backend ships as a Tauri *resource*, so it lands in `$INSTDIR\server\`. These hooks make it
; run: a logon Scheduled Task registered at install, removed at uninstall. The engineer installs
; the app and never has to know a backend exists.
;
; ## Why ExecWait and not Exec
;
; The service registration must finish before the installer reports success. With `Exec` the
; installer closes while PowerShell is still registering, and a user who launches the app
; immediately meets "Connection Lost" from a backend that was never started.
;
; ## Why failures are not fatal
;
; A failed service registration leaves an app that cannot reach its backend -- bad, but far better
; than a failed INSTALL, which leaves a half-written Program Files directory. The install
; completes; `install-service.ps1` can be re-run by hand from `$INSTDIR\server\` to repair it.
;
; ⚠ `-WindowStyle Hidden` keeps a PowerShell console from flashing over the installer UI. The
; scripts' own output still reaches the installer log.

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Registering KMTI 2D Checker backend service..."
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$INSTDIR\server\install-service.ps1" -ServerDir "$INSTDIR\server"'
  Pop $0
  ${If} $0 != 0
    DetailPrint "WARNING: backend service registration returned $0."
    DetailPrint "The app will report 'Connection Lost' until it is registered."
    DetailPrint "Repair by running install-service.ps1 in $INSTDIR\server"
  ${Else}
    DetailPrint "Backend service registered - it starts automatically at logon."
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ; ⚠ BEFORE files are removed, not after. The uninstall script has to stop a process whose
  ; executable lives in $INSTDIR -- and a running exe cannot be deleted, so leaving this until
  ; afterwards makes the uninstall fail to remove its own files AND strand the backend holding
  ; port 8080 until the next reboot.
  DetailPrint "Removing KMTI 2D Checker backend service..."
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$INSTDIR\server\uninstall-service.ps1"'
  Pop $0
  DetailPrint "Backend service removal returned $0."
  ; Give the OS a moment to release the file handles before NSIS starts deleting.
  Sleep 2000
!macroend
