@echo off
REM Sends the daily "collector is alive" report to Telegram right now.
REM Pass --print-only to see it without sending.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
.venv\Scripts\python.exe -m app.notifications.heartbeat %*
echo.
pause
