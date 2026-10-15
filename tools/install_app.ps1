<#
    游戏工具箱 —— 安装程序（用户双击 安装.bat 触发）

    做四件事：
      1. 关掉正在运行的旧版本（python / 浏览器窗口）
      2. 把程序文件复制到安装目录，**保留原来的 userdata**（外观、文字替换、配速预设都在里面）
      3. 建一个桌面快捷方式（图标用 app\favicon.ico）
      4. 启动程序

    可选参数（自动测试用）：
      -Target "路径"     安装到别处（默认 %LOCALAPPDATA%\GameToolbox）
      -NoShortcut        不建桌面快捷方式
      -NoStart           装完不启动
#>
param(
    [string]$Target = "$env:LOCALAPPDATA\GameToolbox",
    [switch]$NoShortcut,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$source = Split-Path -Parent $PSScriptRoot          # 包根目录（本脚本在 tools\ 下）
$name = "b站：@syllo椭圆 游戏工具箱"

Write-Host "  安装目录：$Target" -ForegroundColor Cyan
Write-Host "  来源目录：$source"

# ---- 1. 关掉旧进程（只关命令行里带这个目录的，别误伤别的 python）----
foreach ($proc in Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue) {
    if ($proc.CommandLine -like "*$Target*") {
        Write-Host "  关闭旧进程 PID $($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}
foreach ($proc in Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue) {
    if ($proc.CommandLine -like "*$Target*") {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Milliseconds 600

# ---- 2. 备份 userdata（用户的东西不能丢）----
$userdata = Join-Path $Target "userdata"
$backup = Join-Path $env:TEMP ("gt-userdata-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$hasBackup = $false
if (Test-Path $userdata) {
    Write-Host "  备份 userdata（外观 / 文字 / 预设）…"
    Move-Item $userdata $backup -Force
    $hasBackup = $true
}

# ---- 3. 复制程序文件 ----
New-Item -ItemType Directory -Force -Path $Target | Out-Null
$excludeDirs = @("userdata", ".git", "dist", "__pycache__", ".venv", "venv", "nanoka")
robocopy $source $Target /E /XD @excludeDirs /XF "*.pyc" /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "复制文件失败（robocopy 代码 $LASTEXITCODE）" }

if ($hasBackup) {
    if (Test-Path $userdata) { Remove-Item $userdata -Recurse -Force -ErrorAction SilentlyContinue }
    Move-Item $backup $userdata -Force
    Write-Host "  已恢复 userdata（升级不丢）" -ForegroundColor Green
}

# 防止出现 userdata\userdata 这种嵌套（以前踩过）
if (Test-Path (Join-Path $userdata "userdata")) {
    Write-Host "  发现嵌套 userdata，正在修复…" -ForegroundColor Yellow
    Move-Item (Join-Path $userdata "userdata") $backup -Force
    Remove-Item $userdata -Recurse -Force -ErrorAction SilentlyContinue
    Move-Item $backup $userdata -Force
}

if (-not (Test-Path (Join-Path $Target "start.bat"))) { throw "安装不完整：找不到 start.bat" }

# ---- 4. 桌面快捷方式 ----
if (-not $NoShortcut) {
    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $link = Join-Path $desktop "游戏工具箱.lnk"
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($link)
        $shortcut.TargetPath = Join-Path $Target "start.bat"
        $shortcut.WorkingDirectory = $Target
        $icon = Join-Path $Target "app\favicon.ico"
        if (Test-Path $icon) { $shortcut.IconLocation = $icon }
        $shortcut.Description = $name
        $shortcut.Save()
        Write-Host "  桌面快捷方式：$link" -ForegroundColor Green
    } catch {
        Write-Host "  快捷方式没建成（不影响使用）：$($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# ---- 5. 启动 ----
if (-not $NoStart) {
    Write-Host "  正在启动…" -ForegroundColor Cyan
    Start-Process -FilePath (Join-Path $Target "start.bat") -WorkingDirectory $Target -WindowStyle Minimized
}

Write-Host ""
Write-Host "  安装完成！" -ForegroundColor Green
Write-Host "  * 桌面快捷方式：游戏工具箱"
Write-Host "  * 以后升级：直接跑新的 安装.bat，你的设置和预设都会保留"
Write-Host "  * 手机访问：运行安装目录里的 手机打开.bat"
