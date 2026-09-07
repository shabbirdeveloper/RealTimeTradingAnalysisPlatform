@echo off
REM Starts the market-data collector and leaves it running.
REM
REM %~dp0 is this file's own folder, so it works from any drive or
REM directory -- including double-clicking it from Explorer. Plain "cd" does
REM NOT switch drives on Windows, which is why "cd F:\..." from a C: prompt
REM silently leaves you on C:.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo No virtual environment found in:
  echo   %~dp0.venv
  echo.
  echo Create it first:
  echo   py -3 -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo Starting the collector. LEAVE THIS WINDOW OPEN.
echo.
echo The OTC engine evaluates every 30 seconds. Expect mostly NO_TRADE,
echo each with a reason -- that is the engine working, not failing.
echo Do not press Ctrl+C; that stops collecting.
echo.
echo Use a SECOND window for check.bat and everything else.
echo.
.venv\Scripts\python.exe -m uvicorn app.main:app

echo.
echo The collector has stopped.
pause
