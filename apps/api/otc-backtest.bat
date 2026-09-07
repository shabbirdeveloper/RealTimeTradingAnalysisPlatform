@echo off
REM Does this engine produce enough signals, and do they win? The two
REM numbers that decide whether the platform is usable at all.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
.venv\Scripts\python.exe otc_backtest.py %*
echo.
pause
