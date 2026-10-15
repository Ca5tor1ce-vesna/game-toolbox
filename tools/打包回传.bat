@echo off
chcp 65001 >nul
title 打包改动（发回给助手）
echo.
echo   正在把你的工程 + 你的改动（userdata）打包…
echo.
"%~dp0..\..\..\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" "%~dp0make_source_package.py" --with-userdata
if errorlevel 1 python "%~dp0make_source_package.py" --with-userdata
echo.
echo   包在 dist\ 目录里，名字是 回传-日期时间.zip
echo   把它发给助手即可（助手会在你的改动基础上继续编辑）
echo.
pause
