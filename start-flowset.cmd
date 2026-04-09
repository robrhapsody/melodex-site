@echo off
setlocal
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0start-flowset.ps1"
endlocal
