@echo off
REM What is actually stored versus what the backtest can see.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
echo.
.venv\Scripts\python.exe history_check.py %*
echo.
pause
