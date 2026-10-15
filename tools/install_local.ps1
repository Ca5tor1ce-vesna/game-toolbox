# 把打包好的版本装到固定目录并重启（保留 userdata）。
#
# 教训：直接 Remove-Item 旧目录时，userdata\edge-profile 常被 Edge 占着删不掉，
# 于是 Move-Item 会把新版本「套进」旧目录里，导致 start.bat 找不到。
# 所以这里改成：先把旧目录改名让位 → 放新目录 → 搬回 userdata → 再尽力删旧目录。
param(
    [string]$Zip = "",
    [string]$InstallDir = "$env:LOCALAPPDATA\GameToolbox",
    [int]$Port = 8765,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir

if (-not $Zip) {
    # 本机安装优先用「作者包」——它带后门模块（界面/外观等），只有作者自己的机器需要。
    # 发给别人的是 dist\game-toolbox-latest.zip（不含后门模块，config 里 admin=false）。
    $adminZip = Join-Path $root "dist\game-toolbox-admin-latest.zip"
    $userZip = Join-Path $root "dist\game-toolbox-latest.zip"
    $Zip = if (Test-Path $adminZip) { $adminZip } else { $userZip }
}
if (-not (Test-Path $Zip)) { throw "找不到安装包：$Zip" }

Write-Host "安装包：$Zip"
Write-Host "目标目录：$InstallDir"

# 1. 停掉正在跑的服务与窗口
$procs = @()
$procs += Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*$InstallDir*" }
$procs += Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
    Where-Object { $_.CommandLine -like "*$InstallDir*" -or $_.CommandLine -like "*127.0.0.1:$Port*" }
# start.bat 是 cmd /c 拉起来的，python 退出后这个 cmd 可能还在，
# 它的工作目录正是安装目录，会锁住目录本身（内容能改，目录不能改名）。
$procs += Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
    Where-Object { $_.CommandLine -like "*$InstallDir*" }
Write-Host "停止旧进程：$($procs.Count) 个"
foreach ($proc in $procs) { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3

# 2. 解包到临时目录
$stage = Join-Path $env:TEMP ("gt-stage-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
Expand-Archive -LiteralPath $Zip -DestinationPath $stage -Force
$inner = Get-ChildItem $stage -Directory | Select-Object -First 1
if (-not $inner) { throw "压缩包里没有目录" }
$newFiles = $inner.FullName
Write-Host "解包目录：$newFiles"
if (-not (Test-Path (Join-Path $newFiles "start.bat"))) { throw "包里没有 start.bat，压缩包结构不对" }

# 3. 旧目录改名让位（比直接删安全：删不掉也不会套娃）
$backup = "$InstallDir.old"
if (Test-Path $backup) {
    Remove-Item -Recurse -Force $backup -ErrorAction SilentlyContinue
}
$hasOld = Test-Path $InstallDir
if ($hasOld) {
    # 文件句柄释放可能慢一拍，重试几次再放弃
    $renamed = $false
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try {
            Rename-Item -LiteralPath $InstallDir -NewName (Split-Path -Leaf $backup) -ErrorAction Stop
            $renamed = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $renamed) {
        Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
        throw "旧目录改名失败（仍有进程占用 $InstallDir）。应用没有被改动，可以直接重试。"
    }
}

# 4. 放进新版本
Move-Item -LiteralPath $newFiles -Destination $InstallDir

# 5. 搬回 userdata（配装预设、图片缓存、窗口配置）
#    坑：包里自带一个 userdata 占位目录，直接 Move-Item 到已存在的目标时，
#    旧的 userdata 会被塞进包里那个里面（变成 userdata\userdata），应用就读不到预设。
#    所以先把目标清掉再搬。
if ($hasOld -and (Test-Path "$backup\userdata")) {
    if (Test-Path "$InstallDir\userdata") {
        Remove-Item -Recurse -Force "$InstallDir\userdata" -ErrorAction SilentlyContinue
    }
    Move-Item -LiteralPath "$backup\userdata" -Destination "$InstallDir\userdata" -Force
    Write-Host "已恢复 userdata"
}

# 6. 尽力清掉旧目录（占用中就留着，不影响使用）
if ($hasOld) {
    Remove-Item -Recurse -Force $backup -ErrorAction SilentlyContinue
    if (Test-Path $backup) { Write-Host "旧目录暂时删不掉（被占用），已保留在 $backup" }
}
Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue

# 7. 校验
$version = (Select-String -Path "$InstallDir\core\__init__.py" -Pattern '__version__').Line -replace '.*"([^"]+)".*', '$1'
if (-not (Test-Path "$InstallDir\start.bat")) { throw "安装后找不到 start.bat" }
if (Test-Path "$InstallDir\userdata\userdata") { throw "userdata 被套娃了（安装流程有问题）" }
Write-Host "安装完成：v$version"

# 8. 启动
if (-not $NoStart) {
    Start-Process -FilePath "$InstallDir\start.bat" -WorkingDirectory $InstallDir -WindowStyle Minimized | Out-Null
    Start-Sleep -Seconds 10
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 8
        Write-Host "服务已启动：v$($health.version)"
    } catch {
        Write-Host "服务未能连上，请检查窗口提示"
    }
}
