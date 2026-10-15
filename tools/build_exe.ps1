# Build a single-file exe with PyInstaller (ASCII only: PowerShell 5.1 reads
# non-ASCII .ps1 as ANSI unless it has a BOM, which breaks parsing).
$ErrorActionPreference = 'Continue'
$py = "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$root = "C:\Users\Administrator\Documents\deepseek-harness\default-workspace\game-toolbox"
$tmp = "$env:TEMP\gt-pyi"
$build = "$env:TEMP\gt-pyi-build"

Write-Host "=== 1. install PyInstaller into a temp dir ==="
if (-not (Test-Path "$tmp\PyInstaller")) {
    & $py -m pip install --disable-pip-version-check -q --target $tmp pyinstaller 2>&1 | Select-Object -Last 4
}
if (-not (Test-Path "$tmp\PyInstaller")) { Write-Host "FAILED: pyinstaller not installed"; exit 1 }
Write-Host "  pyinstaller ready"

# Do not pass userdata or edge-profile to --add-data. The exe writes
# userdata next to itself; a bundled profile ships browser history.
Write-Host "=== 2. build (onefile, no console, icon, bundled app+modules) ==="
$env:PYTHONPATH = $tmp
Remove-Item "$root\dist\exe" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $build -Recurse -Force -ErrorAction SilentlyContinue
& $py -m PyInstaller --noconfirm --clean --onefile --noconsole --name GameToolbox --icon "$root\app\favicon.ico" --add-data "$root\app;app" --add-data "$root\modules;modules" --distpath "$root\dist\exe" --workpath $build --specpath $build "$root\run.py" 2>&1 | Select-Object -Last 14

Write-Host "=== 3. result ==="
$exe = "$root\dist\exe\GameToolbox.exe"
if (Test-Path $exe) {
    $size = (Get-Item $exe).Length / 1MB
    Write-Host ("  OK  GameToolbox.exe  {0:N1} MB" -f $size)
} else {
    Write-Host "  FAILED: exe not produced"
}
