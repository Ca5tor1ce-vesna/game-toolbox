<#
    游戏工具箱（exe 版）安装程序 —— 由 安装.bat 调用

      1. 关掉正在运行的旧实例
      2. 复制程序到安装目录，保留原来的 userdata（外观 / 文字 / 预设）
      3. 桌面 + 开始菜单快捷方式（图标用 exe 自带的）
      4. 启动

    参数（自动测试用）：-Target 路径  -NoShortcut  -NoStartMenu  -NoStart
#>
param(
    [string]$Target = "$env:LOCALAPPDATA\游戏工具箱",
    [switch]$NoShortcut,
    [switch]$NoStartMenu,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $Target "GameToolbox.exe"

# exe 在哪：发布包里放在根目录；在源码目录里跑时，build_exe.ps1 输出在 dist\exe\。
# 先找到再动手（旧版先整树复制、最后才检查，必然失败还留下一堆源码）。
$sourceExe = $null
foreach ($candidate in @((Join-Path $source "GameToolbox.exe"), (Join-Path $source "dist\exe\GameToolbox.exe"))) {
    if (Test-Path $candidate) { $sourceExe = $candidate; break }
}
if (-not $sourceExe) { throw "找不到 GameToolbox.exe：请先运行 tools\build_exe.ps1，或使用 exe 发布包" }

Write-Host "  安装目录：$Target" -ForegroundColor Cyan

# 1. 关掉正在跑的旧实例（按路径过滤，别误伤别的程序）
foreach ($proc in Get-Process -Name "GameToolbox" -ErrorAction SilentlyContinue) {
    if ($proc.Path -and $proc.Path -like "$Target*") {
        Write-Host "  关闭旧实例 PID $($proc.Id)"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Milliseconds 500

# 2. 备份 userdata
$userdata = Join-Path $Target "userdata"
$backup = Join-Path $env:TEMP ("gt-appdata-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$hasBackup = $false
if (Test-Path $userdata) {
    Write-Host "  备份 userdata（外观 / 文字 / 预设）…"
    Move-Item $userdata $backup -Force
    $hasBackup = $true
}

# 3. 复制文件
New-Item -ItemType Directory -Force -Path $Target | Out-Null
# 单文件 exe 已经自带 app / modules / docs 和默认配置；只装 exe + 卸载脚本。
# 不再整树复制：那样会把源码、dist\、带 admin:true 的 config.json 一起装给用户。
Copy-Item $sourceExe $exe -Force
Copy-Item (Join-Path $source "卸载.bat") (Join-Path $Target "卸载.bat") -Force
New-Item -ItemType Directory -Force -Path (Join-Path $Target "tools") | Out-Null
Copy-Item (Join-Path $source "tools\uninstall.ps1") (Join-Path $Target "tools\uninstall.ps1") -Force

if ($hasBackup) {
    if (Test-Path $userdata) { Remove-Item $userdata -Recurse -Force -ErrorAction SilentlyContinue }
    Move-Item $backup $userdata -Force
    Write-Host "  已恢复 userdata（升级不丢）" -ForegroundColor Green
}

if (-not (Test-Path $exe)) { throw "安装不完整：找不到 GameToolbox.exe" }

# 4. 快捷方式
$shell = New-Object -ComObject WScript.Shell
if (-not $NoShortcut) {
    try {
        $link = Join-Path ([Environment]::GetFolderPath("Desktop")) "游戏工具箱.lnk"
        $sc = $shell.CreateShortcut($link)
        $sc.TargetPath = $exe
        $sc.WorkingDirectory = $Target
        $sc.IconLocation = "$exe,0"
        $sc.Description = "b站：@syllo椭圆 游戏工具箱"
        $sc.Save()
        Write-Host "  桌面快捷方式：$link" -ForegroundColor Green
    } catch { Write-Host "  桌面快捷方式没建成：$($_.Exception.Message)" -ForegroundColor Yellow }
}
if (-not $NoStartMenu) {
    try {
        $menu = Join-Path ([Environment]::GetFolderPath("Programs")) "游戏工具箱.lnk"
        $sc = $shell.CreateShortcut($menu)
        $sc.TargetPath = $exe
        $sc.WorkingDirectory = $Target
        $sc.IconLocation = "$exe,0"
        $sc.Description = "b站：@syllo椭圆 游戏工具箱"
        $sc.Save()
        Write-Host "  开始菜单：$menu" -ForegroundColor Green
    } catch { Write-Host "  开始菜单没建成：$($_.Exception.Message)" -ForegroundColor Yellow }
}

# 5. 启动
if (-not $NoStart) {
    Write-Host "  正在启动…" -ForegroundColor Cyan
    Start-Process -FilePath $exe -WorkingDirectory $Target
}

Write-Host ""
Write-Host "  安装完成！桌面/开始菜单都能打开「游戏工具箱」" -ForegroundColor Green
Write-Host "  卸载：运行安装目录里的 卸载.bat"
