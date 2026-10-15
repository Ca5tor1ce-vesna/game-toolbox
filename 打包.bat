@echo off
rem Build a distributable zip under dist\
rem Keep this file pure ASCII (see start.bat for why).
chcp 65001 >nul
cd /d "%~dp0"

set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"

%PS% -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Package %*

echo.
echo [package] finished. The zip is in the dist\ folder.
pause
