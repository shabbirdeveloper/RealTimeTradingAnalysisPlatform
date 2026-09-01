@echo off
REM Tests whether any single feature predicts short-horizon direction.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo No venv & pause & exit /b 1 )
.venv\Scripts\python.exe analyze_features.py %*
echo.
pause
