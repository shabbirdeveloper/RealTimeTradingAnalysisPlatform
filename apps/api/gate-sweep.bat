@echo off
REM Measures what loosening the multi-timeframe gate would actually produce.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
.venv\Scripts\python.exe gate_sweep.py %*
echo.
pause
