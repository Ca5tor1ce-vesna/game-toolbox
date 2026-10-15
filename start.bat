@echo off
rem Game Toolbox -- desktop window mode. The app quits when you close the window.
rem NOTE: keep this file pure ASCII. cmd.exe parses .bat in the OEM codepage, so
rem non-ASCII text in a UTF-8 batch file gets mis-parsed and breaks the script.
chcp 65001 >nul
cd /d "%~dp0"

set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"

%PS% -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
  echo.
  echo [toolbox] exited with code %CODE% -- see the messages above.
  pause
)
