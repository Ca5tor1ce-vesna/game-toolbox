# Build a single-file exe with PyInstaller (ASCII only: PowerShell 5.1 reads
# non-ASCII .ps1 as ANSI unless it has a BOM, which breaks parsing).
$ErrorActionPreference = 'Continue'
# Repo root = parent of tools\ (no machine-specific paths).
$root = Split-Path -Parent $PSScriptRoot
# Python: $env:GT_PYTHON if set, else the py launcher, else python on PATH.
$py = $env:GT_PYTHON
$pyArgs = @()
if (-not $py) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $py = "py"; $pyArgs = @("-3") }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }
    else { Write-Host "FAILED: Python not found (install Python 3.8+ or set GT_PYTHON)"; exit 1 }
}
$tmp = "$env:TEMP\gt-pyi"
$build = "$env:TEMP\gt-pyi-build"

Write-Host "=== 1. install PyInstaller into a temp dir ==="
if (-not (Test-Path "$tmp\PyInstaller")) {
    & $py @pyArgs -m pip install --disable-pip-version-check -q --target $tmp pyinstaller 2>&1 | Select-Object -Last 4
}
if (-not (Test-Path "$tmp\PyInstaller")) { Write-Host "FAILED: pyinstaller not installed"; exit 1 }
Write-Host "  pyinstaller ready"

# Do not pass userdata or edge-profile to --add-data. The exe writes
# userdata next to itself; a bundled profile ships browser history.
Write-Host "=== 2. build (onefile, no console, icon, bundled app+modules+docs) ==="
$env:PYTHONPATH = $tmp
Remove-Item "$root\dist\exe" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $build -Recurse -Force -ErrorAction SilentlyContinue
& $py @pyArgs -m PyInstaller --noconfirm --clean --onefile --noconsole --name GameToolbox --icon "$root\app\favicon.ico" --add-data "$root\app;app" --add-data "$root\modules;modules" --add-data "$root\docs;docs" --distpath "$root\dist\exe" --workpath $build --specpath $build "$root\run.py" 2>&1 | Select-Object -Last 14

Write-Host "=== 3. result ==="
$exe = "$root\dist\exe\GameToolbox.exe"
if (Test-Path $exe) {
    $size = (Get-Item $exe).Length / 1MB
    Write-Host ("  OK  GameToolbox.exe  {0:N1} MB" -f $size)
} else {
    Write-Host "  FAILED: exe not produced"
}
