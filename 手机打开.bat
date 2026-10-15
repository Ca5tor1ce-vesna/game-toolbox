@echo off
rem Game Toolbox -- phone access over the local network (LAN).
rem It serves the single-file speed-plan page and prints the address to open on your phone.
rem Keep this window open while using the phone; press Ctrl+C here to stop.
rem NOTE: keep this file pure ASCII (cmd.exe parses .bat in the OEM codepage).
chcp 65001 >nul
cd /d "%~dp0"

set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"

%PS% -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Phone %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
  echo.
  echo [toolbox] exited with code %CODE% -- see the messages above.
  pause
)
