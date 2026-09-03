' ============================================================================
' Launch DraftCheck_Server.exe with NO visible window.
' ============================================================================
'
' Why a VBScript and not the Scheduled Task's own "Hidden" option:
'
' The server is built as a CONSOLE application on purpose -- an operator can double-click the exe
' to watch it start and read the banner when something is wrong. A console application launched by
' a logon-triggered task still flashes a window, and the task's "Hidden" checkbox does not reliably
' suppress it for console subsystems; it hides the TASK, not the child console.
'
' WScript.Shell.Run's second argument is the window style, and 0 means hidden. It is the shortest
' dependency-free way on Windows to start a console process with no window at all, and it needs no
' extra binary in the installer.
'
' ⚠ Third argument is False = do not wait. The task must return immediately; the server runs for
' the life of the session.
'
' Diagnostics are NOT lost by hiding the window: the backend writes to storage\logs\backend\*.log
' beside the executable. To see the console instead, run the .exe directly.

Option Explicit

Dim shell, fso, here, exePath

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Resolve relative to this script so the whole folder can be moved or installed anywhere.
here = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = fso.BuildPath(here, "DraftCheck_Server.exe")

If Not fso.FileExists(exePath) Then
    ' Surface this one loudly. A silent no-op here means the app shows "Connection Lost" forever
    ' with nothing anywhere explaining why.
    MsgBox "DraftCheck: backend executable not found at" & vbCrLf & exePath, _
           vbCritical, "DraftCheck"
    WScript.Quit 1
End If

' Working directory is the server folder, so anything resolving a relative path lands beside the
' executable rather than wherever the task scheduler happened to start us.
shell.CurrentDirectory = here
shell.Run """" & exePath & """", 0, False

WScript.Quit 0
