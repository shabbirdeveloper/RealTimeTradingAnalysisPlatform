@echo off
REM Splits the backtest every way the data allows: which slice loses?
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
.venv\Scripts\python.exe breakdown.py %*
echo.
pause
