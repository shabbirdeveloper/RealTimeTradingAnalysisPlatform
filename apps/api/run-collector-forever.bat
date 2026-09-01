@echo off
setlocal
REM ===========================================================================
REM Runs the collector and restarts it if it exits.
REM
REM The collector has to run continuously: it accumulates candle history and
REM resolves signals when they reach expiry. Every gap is history that never
REM gets collected, and signals that never get scored.
REM
REM This wrapper handles a crash. It does NOT handle the machine sleeping or
REM the window being closed -- for that, run install-autostart.bat once.
REM ===========================================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No virtual environment found in %~dp0.venv
  echo   py -3 -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

set ATTEMPT=0

:run
set /a ATTEMPT+=1
echo.
echo [%DATE% %TIME%] starting collector (run #%ATTEMPT%)
echo Polls every 10 minutes. Quiet between cycles is normal -- do not Ctrl+C.
.venv\Scripts\python.exe -m uvicorn app.main:app

REM A clean Ctrl+C exits here too. That is deliberate: an operator stopping
REM the collector on purpose should not be fought by a restart loop, so the
REM pause below gives a window to close it.
echo.
echo [%DATE% %TIME%] collector exited. Restarting in 10 seconds.
echo Close this window now to stop it for good.
timeout /t 10 /nobreak >nul
goto run
