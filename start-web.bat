@echo off
rem Game Toolbox -- web mode. Opens your default browser; the service keeps running
rem until you press Ctrl+C in this window.
rem NOTE: keep this file pure ASCII (see start.bat for why).
chcp 65001 >nul
cd /d "%~dp0"

set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"

%PS% -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Web %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
  echo.
  echo [toolbox] exited with code %CODE% -- see the messages above.
  pause
)
