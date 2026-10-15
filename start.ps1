# 游戏实用工具箱 —— Windows 启动脚本
# 用法：start.bat（桌面窗口） / start-web.bat（仅网页） / 手机打开.bat（手机访问）
#       自检.bat / 打包.bat
#
# 这个脚本只干一件事：找到能用的 Python，然后把对应的入口跑起来。

param(
    [switch]$Web,
    [switch]$Tests,
    [switch]$Package,
    [switch]$Phone
)

# 其余参数一律透传给 run.py。
# 注意：必须用自动变量 $args，不能用自定义的 [string[]]$ExtraArgs —— 以 - 或 -- 开头的参数
# 会被 PowerShell 当成“参数名”而落到 $args 里，自定义变量接不到，会静默丢参数（踩过）。
# 例：start.bat --port 9000  →  $args = @('--port','9000')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# 控制台切到 UTF-8，中文和图标才能正常显示（切不了也不影响运行）
try {
    $null = chcp 65001
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

function Find-Python {
    $candidates = New-Object System.Collections.Generic.List[string]

    # 1) 项目自带虚拟环境（最优先）
    $candidates.Add((Join-Path $root '.venv\Scripts\python.exe'))

    # 2) 用户级安装的 Python
    if ($env:LOCALAPPDATA) {
        $userPython = Join-Path $env:LOCALAPPDATA 'Programs\Python'
        if (Test-Path $userPython) {
            Get-ChildItem $userPython -Filter 'python.exe' -Recurse -Depth 2 -ErrorAction SilentlyContinue |
                ForEach-Object { $candidates.Add($_.FullName) }
        }
    }

    # 3) 根目录下的 Python3x
    Get-ChildItem 'C:\' -Filter 'Python3*' -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { $candidates.Add((Join-Path $_.FullName 'python.exe')) }

    # 4) DSH 自带的 Python（这台机器上一定有）
    if ($env:USERPROFILE) {
        $candidates.Add((Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'))
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return @($candidate)
        }
    }

    # 5) py 启动器
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, '-3') }

    # 6) PATH 上的 python（排除微软商店的占位符）
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike '*WindowsApps*') {
        return @($python.Source)
    }

    return $null
}

# 注意：必须用 @() 包住。PowerShell 函数返回单元素数组时会被“拆包”成字符串，
# 那样 $found[0] 就变成了路径的第一个字符（这个坑真的踩过，表现是“用的 Python：C”）。
$found = @(Find-Python)
if (-not $found -or $found.Count -eq 0) {
    Write-Host ''
    Write-Host '  [工具箱] 没有找到可用的 Python。' -ForegroundColor Red
    Write-Host '  装一个 Python 3.10+ 就好（安装时勾选 Add to PATH）：https://www.python.org/downloads/'
    Write-Host '  或者把 Python 目录里的 python.exe 放到这个项目下的 .venv\Scripts\ 里。'
    Write-Host ''
    exit 1
}

$exe = $found[0]
$pre = @()
if ($found.Count -gt 1) { $pre = $found[1..($found.Count - 1)] }

if ($Package) {
    $cmdArgs = @((Join-Path $root 'make_package.py'))
} elseif ($Tests) {
    $cmdArgs = @((Join-Path $root 'tests\test_toolbox.py'))
} elseif ($Phone) {
    # 手机访问：把单文件网页版挂到局域网，并打印手机能打开的地址
    $cmdArgs = @((Join-Path $root 'tools\serve_web.py'))
} else {
    $cmdArgs = @((Join-Path $root 'run.py'))
    if ($Web) { $cmdArgs += '--web' }
}
if ($args.Count -gt 0) { $cmdArgs += $args }

Write-Host "[工具箱] 用的 Python：$exe" -ForegroundColor DarkGray
& $exe @pre @cmdArgs
exit $LASTEXITCODE
