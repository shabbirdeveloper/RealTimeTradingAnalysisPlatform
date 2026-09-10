@echo off
REM M1 history for the 5-minute engine. The live collector only ever holds
REM fifteen hours of it, which is exactly the warm-up -- leaving nothing to
REM backtest. This fetches days of it in two or three requests.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
echo.
.venv\Scripts\python.exe backfill_m1.py %*
echo.
pause
