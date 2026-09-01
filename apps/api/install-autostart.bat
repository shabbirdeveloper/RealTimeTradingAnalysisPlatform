@echo off
setlocal
REM ===========================================================================
REM Registers the collector to start automatically at logon.
REM
REM Run this ONCE. After it, the collector survives closing the terminal and
REM restarts with the machine -- the two ways it has died so far.
REM
REM Uses a per-user scheduled task, so it needs no administrator rights and
REM touches nothing outside this account.
REM ===========================================================================
cd /d "%~dp0"

set TASK=NorthFXTradeCollector

schtasks /query /tn "%TASK%" >nul 2>&1
if %ERRORLEVEL%==0 (
  echo Task "%TASK%" already exists. Replacing it.
  schtasks /delete /tn "%TASK%" /f >nul
)

schtasks /create /tn "%TASK%" /tr "\"%~dp0run-collector-forever.bat\"" /sc onlogon /rl limited /f
if not %ERRORLEVEL%==0 (
  echo.
  echo Could not create the scheduled task.
  pause
  exit /b 1
)

echo.
echo Registered. The collector will start automatically at every logon.
echo.
echo   Start it now without logging out:  schtasks /run /tn "%TASK%"
echo   Stop it:                           schtasks /end /tn "%TASK%"
echo   Remove it:                         schtasks /delete /tn "%TASK%" /f
echo.
echo NOTE: this does not stop the machine sleeping. A laptop that sleeps still
echo stops collecting. For genuinely continuous operation the collector needs
echo to run somewhere that stays awake.
echo.
pause
