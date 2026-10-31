@echo off
pwsh -NoProfile -File "%~dp0launchers\start-alysia.ps1"
if errorlevel 1 pause
