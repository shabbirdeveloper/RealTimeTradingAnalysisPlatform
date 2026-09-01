@echo off
REM Answers "is NO TRADE always right?" by replaying real stored history.
REM Changes nothing about the running engine -- this is measurement only.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No virtual environment found in %~dp0.venv
  pause
  exit /b 1
)

.venv\Scripts\python.exe sweep.py %*
echo.
pause
