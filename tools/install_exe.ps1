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
# userdata 在 exe 旁边，不在 _internal 里。edge-profile 是本机 Edge 配置，不能装给别人。
robocopy $source $Target /E /XD userdata edge-profile /XF "*.pyc" /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "复制文件失败（robocopy $LASTEXITCODE）" }

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
