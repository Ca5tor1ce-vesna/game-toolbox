@echo off
chcp 65001 >nul
title 游戏工具箱 卸载
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\uninstall.ps1"
