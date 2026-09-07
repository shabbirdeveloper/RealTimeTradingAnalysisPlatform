@echo off
REM Does this engine produce enough signals, and do they win? The two
REM numbers that decide whether the platform is usable at all.
REM
REM Replays what the COLLECTOR SAVED -- it does not fetch, so there is
REM nothing to replay until the collector has been running for a while.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
echo.
echo Running the backtest. The report prints below AND is saved to the
echo backtests\ folder next to this file, so it can be reread or sent.
echo.
.venv\Scripts\python.exe otc_backtest.py %*
echo.
pause
