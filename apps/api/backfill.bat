@echo off
REM Fetches historical candles so the engine can warm up. Preview by default.
REM Pass --run to actually fetch:  backfill.bat --run
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No virtual environment found in %~dp0.venv
  pause
  exit /b 1
)

.venv\Scripts\python.exe backfill.py %*
echo.
pause
