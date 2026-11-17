@echo off
title Aurora Companion Setup
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\bootstrap.ps1" %*
if errorlevel 1 (
  echo.
  echo Setup did not finish. See the messages above, or the logs folder.
)
echo.
pause
