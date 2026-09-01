@echo off
REM Reports where the signal pipeline is stuck. Safe to run any time.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No virtual environment found in %~dp0.venv
  pause
  exit /b 1
)

.venv\Scripts\python.exe diagnose.py
echo.
pause
