@echo off
REM Milestone 1: do our candles match the broker's own? Nothing runs until they do.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
.venv\Scripts\python.exe verify_feed.py %*
echo.
pause
