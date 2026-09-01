@echo off
setlocal
REM Removes the logon autostart created by install-autostart.bat.
set "LAUNCHER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\NorthFXTrade Collector.bat"

if exist "%LAUNCHER%" (
  del "%LAUNCHER%"
  echo Removed: %LAUNCHER%
) else (
  echo Nothing to remove — no startup launcher found.
)

REM Also clean up the scheduled task, in case an earlier version created one.
schtasks /query /tn "NorthFXTradeCollector" >nul 2>&1
if %ERRORLEVEL%==0 schtasks /delete /tn "NorthFXTradeCollector" /f >nul 2>&1

echo.
echo The collector will no longer start at logon. Any running instance keeps
echo going until you close its window.
echo.
pause
