@echo off
chcp 65001 >nul
title 游戏工具箱 安装程序
echo.
echo   ============================================
echo      b站：@syllo椭圆  游戏工具箱
echo   ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_exe.ps1" %*
echo.
pause
