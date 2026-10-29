$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$runDir = Join-Path $tempRoot ('game-toolbox-ci-' + [guid]::NewGuid().ToString('N'))
$oldData = $env:GT_USERDATA
$oldOffline = $env:GT_CI_OFFLINE_DIR
$service = $null
$browser = $null

function Get-FreePort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return $listener.LocalEndpoint.Port } finally { $listener.Stop() }
}

function Wait-Http($url) {
    for ($i = 0; $i -lt 100; $i++) {
        if ($service -and $service.HasExited) { throw '隔离服务意外退出' }
        try { return Invoke-RestMethod -Uri $url -TimeoutSec 1 } catch { Start-Sleep -Milliseconds 200 }
    }
    throw "服务未就绪：$url"
}

try {
    New-Item -ItemType Directory -Path $runDir | Out-Null
    $env:GT_USERDATA = Join-Path $runDir 'userdata'
    $env:GT_CI_OFFLINE_DIR = Join-Path $runDir 'offline'
    $python = (Get-Command python -All -CommandType Application | Where-Object { $_.Source -notmatch '[\\/]WindowsApps[\\/]' } | Select-Object -First 1).Source
    if (-not $python) { throw '找不到 Python 安装路径' }
    $port = Get-FreePort
    $service = Start-Process -FilePath $python -WorkingDirectory $workspace -WindowStyle Hidden -PassThru -ArgumentList @('run.py', 'run', '--web', '--no-open', '--host', '127.0.0.1', '--port', $port, '--no-watchdog')
    $null = Wait-Http "http://127.0.0.1:$port/api/registry"
    & $python -c 'from pathlib import Path; import os; from tools import make_web_standalone as b; b.DIST=Path(os.environ["GT_CI_OFFLINE_DIR"]); b.build(with_theme=False,out_name="preview.html")'
    if ($LASTEXITCODE -ne 0) { throw '离线页面生成失败' }
    $edge = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $edge) { throw '找不到 Microsoft Edge' }

    foreach ($test in @('verify_redesign_ui.mjs', 'verify_text_overrides.mjs', 'verify_team_ui.mjs')) {
        $debug = Get-FreePort
        $profile = Join-Path $runDir ('profile-' + $test)
        $browser = Start-Process -FilePath $edge -WindowStyle Hidden -PassThru -ArgumentList @('--headless=new', '--disable-gpu', "--remote-debugging-port=$debug", "--user-data-dir=`"$profile`"", 'about:blank')
        $null = Wait-Http "http://127.0.0.1:$debug/json/list"
        $argsForTest = @((Join-Path $PSScriptRoot $test), $port, $debug)
        if ($test -eq 'verify_team_ui.mjs') {
            $argsForTest += @((Join-Path $runDir 'screenshots'), (Join-Path $env:GT_CI_OFFLINE_DIR 'preview.html'))
        }
        & node @argsForTest
        if ($LASTEXITCODE -ne 0) { throw "浏览器检查失败：$test" }
        Stop-Process -Id $browser.Id -Force -ErrorAction SilentlyContinue
        $browser = $null
    }
} finally {
    if ($browser) { Stop-Process -Id $browser.Id -Force -ErrorAction SilentlyContinue }
    if ($service) { Stop-Process -Id $service.Id -Force -ErrorAction SilentlyContinue }
    $env:GT_USERDATA = $oldData
    $env:GT_CI_OFFLINE_DIR = $oldOffline
    $resolved = [IO.Path]::GetFullPath($runDir)
    if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -match '^game-toolbox-ci-[a-f0-9]{32}$' -and (Test-Path -LiteralPath $resolved)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
