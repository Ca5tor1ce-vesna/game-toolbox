<#
    游戏工具箱 卸载 —— 由安装目录里的 卸载.bat 调用
      1. 关掉程序
      2. 问是否保留 userdata（外观 / 文字 / 预设）；保留就备份到桌面
      3. 删掉桌面 / 开始菜单快捷方式
      4. 删掉整个安装目录（用延迟命令删，因为脚本自己就在里面）
#>
param([switch]$Force, [switch]$KeepUserData)

$target = Split-Path -Parent $PSScriptRoot
Write-Host "  安装目录：$target" -ForegroundColor Cyan

foreach ($proc in Get-Process -Name "GameToolbox" -ErrorAction SilentlyContinue) {
    if ($proc.Path -and $proc.Path -like "$target*") {
        Write-Host "  关闭程序 PID $($proc.Id)"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Milliseconds 500

# 是否保留 userdata
$keep = $KeepUserData
if (-not $Force) {
    $answer = Read-Host "  保留你的设置和预设（userdata）吗？保留请输入 Y"
    if ($answer -eq "Y" -or $answer -eq "y") { $keep = $true }
}
if ($keep -and (Test-Path (Join-Path $target "userdata"))) {
    $dest = Join-Path ([Environment]::GetFolderPath("Desktop")) "游戏工具箱-userdata备份"
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue }
    Copy-Item (Join-Path $target "userdata") $dest -Recurse -Force
    Write-Host "  设置已备份到桌面：$dest" -ForegroundColor Green
}

foreach ($link in @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "游戏工具箱.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "游戏工具箱.lnk")
)) {
    if (Test-Path $link) { Remove-Item $link -Force -ErrorAction SilentlyContinue; Write-Host "  已删除快捷方式：$link" }
}

Write-Host "  正在删除安装目录…" -ForegroundColor Cyan
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "timeout /t 2 >nul & rmdir /s /q `"$target`"" -WindowStyle Hidden
Write-Host "  卸载完成（窗口会自动关闭）" -ForegroundColor Green
