# Launches the AI-2D-Checker in Streamlined Prototype Mode (2D CAD Workspace only)
$PSScriptRootFolder = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$PSScriptRootFolder\start_desktop.ps1" -Prototype
