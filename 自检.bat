@echo off
rem Self-test: checks the speed formula and the gacha probability model.
rem Keep this file pure ASCII (see start.bat for why).
chcp 65001 >nul
cd /d "%~dp0"

set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"

%PS% -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Tests %*

echo.
echo [self-test] finished. If you see "OK" above, every check passed.
pause
