@echo off
chcp 65001 >nul
title 打包改动（发回给助手）
echo.
echo   正在把你的工程 + 你的改动（userdata）打包…
echo.
rem 找 Python：优先 py 启动器（官方安装包自带），否则用 PATH 里的 python
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% "%~dp0make_source_package.py" --with-userdata
if errorlevel 1 echo   打包失败：请确认已安装 Python 3.8+（python.org），并勾选了 Add to PATH
echo.
echo   包在 dist\ 目录里，名字是 回传-日期时间.zip
echo   把它发给助手即可（助手会在你的改动基础上继续编辑）
echo.
pause
