@echo off
REM Verifies the Deriv synthetic feed against the live API.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
.venv\Scripts\python.exe deriv_check.py %*
echo.
pause
