@echo off
rem Same as Start_Aurora.bat but keeps a console window open with log output (for bug reports).
cd /d "%~dp0"
set "AURORA_ROOT=%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Aurora is not set up yet - run Setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "%~dp0Aurora_Companion.py"
pause
