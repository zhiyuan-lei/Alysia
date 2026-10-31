@echo off
pwsh -NoProfile -File "%~dp0launchers\start-comfyui.ps1"
if errorlevel 1 pause
