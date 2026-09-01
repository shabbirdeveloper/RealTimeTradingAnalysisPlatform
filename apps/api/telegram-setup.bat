@echo off
REM Finds your Telegram chat id and sends a test message.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No virtual environment found in %~dp0.venv
  pause
  exit /b 1
)
.venv\Scripts\python.exe telegram_setup.py
echo.
pause
