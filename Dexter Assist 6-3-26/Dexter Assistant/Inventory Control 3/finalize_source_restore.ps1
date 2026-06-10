param(
  [string]$ProjectRoot = "C:\Users\arnol\OneDrive\Desktop\AIO-Python\Restaurant Management\Inventory Control 3"
)

$ErrorActionPreference = "Stop"

function Test-IsWrapper([string]$path) {
  if (!(Test-Path $path)) { return $false }
  $raw = Get-Content -Path $path -Raw
  return $raw -match "runpy\.run_path" -and $raw -match "\.pyc"
}

$appPath = Join-Path $ProjectRoot "app.py"
$launcherPath = Join-Path $ProjectRoot "inventory_control3_launcher.py"
$mlPath = Join-Path $ProjectRoot "ml_trends.py"
$pyExe = Join-Path $ProjectRoot "venv\Scripts\python.exe"

if (!(Test-Path $pyExe)) {
  throw "Missing Python executable: $pyExe"
}

$appWrapper = Test-IsWrapper $appPath
$launcherWrapper = Test-IsWrapper $launcherPath

Write-Host "Project: $ProjectRoot"
Write-Host "app.py is wrapper: $appWrapper"
Write-Host "inventory_control3_launcher.py is wrapper: $launcherWrapper"
Write-Host "ml_trends.py exists: $(Test-Path $mlPath)"

if ($appWrapper -or $launcherWrapper -or !(Test-Path $mlPath)) {
  Write-Host "Restore not complete yet. Run this script again after OneDrive restore." -ForegroundColor Yellow
  exit 2
}

Write-Host "Source restore detected. Running syntax validation..." -ForegroundColor Cyan
& $pyExe -m py_compile $appPath
& $pyExe -m py_compile $launcherPath
& $pyExe -m py_compile $mlPath

Write-Host "Syntax validation passed." -ForegroundColor Green
Write-Host "Optional smoke test command:" -ForegroundColor Cyan
Write-Host "  & '$pyExe' '$appPath'"
