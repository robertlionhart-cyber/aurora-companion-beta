@echo off
cd /d "%~dp0"
set "AURORA_ROOT=%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "%~dp0Aurora_Companion.py"
  exit /b 0
)
echo Aurora is not set up yet. Starting Setup...
call "%~dp0Setup.bat"
