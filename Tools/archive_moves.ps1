# Archive moves: relocate duplicate/backup/snapshot folders out of workspace.
# Run from anywhere; uses absolute paths.

$src = 'C:\Users\arnol\OneDrive\Desktop\AIO-Python'
$dst = 'C:\Users\arnol\OneDrive\Desktop\AIO-Python-Archive'
$manifest = Join-Path $dst 'MOVE_MANIFEST.txt'

"# AIO-Python archive move manifest"             | Out-File $manifest -Encoding utf8
"# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Add-Content $manifest
"# Source:    $src"                              | Add-Content $manifest
"# Dest:      $dst"                              | Add-Content $manifest
""                                               | Add-Content $manifest

$moves = @(
  @{ From = '_dexter_assistant_build';                                       To = 'dexter_build\_dexter_assistant_build' },
  @{ From = 'AIO_Snapshots';                                                 To = 'snapshots\AIO_Snapshots' },
  @{ From = 'build';                                                         To = 'misc\build' },
  @{ From = 'AIO_Enclosed_Apps';                                             To = 'enclosed\AIO_Enclosed_Apps' },
  @{ From = 'AIO_Consolidated_Clean';                                        To = 'consolidated\AIO_Consolidated_Clean' },
  @{ From = 'AIO_Consolidated_Full';                                         To = 'consolidated\AIO_Consolidated_Full' },
  @{ From = 'ProductMixRestaurantDB_backup_20260509_021451';                 To = 'app_backups\ProductMixRestaurantDB_backup_20260509_021451' },
  @{ From = 'Dexter Assistant_backup_20260524';                              To = 'app_backups\Dexter Assistant_backup_20260524' },
  @{ From = 'RestaurantStack-Combined';                                      To = 'misc\RestaurantStack-Combined' },
  @{ From = 'AIO_Tidy';                                                      To = 'misc\AIO_Tidy' },
  @{ From = 'archived_files';                                                To = 'misc\archived_files' },
  @{ From = 'Restaurant Management\Manager App Backup';                      To = 'manager_app_old\Manager App Backup' },
  @{ From = 'Restaurant Management\Manager App Backup 2025-11-23_04-05-42'; To = 'manager_app_old\Manager App Backup 2025-11-23_04-05-42' }
)

$total = $moves.Count
$i = 0
$failed = @()

foreach ($m in $moves) {
  $i++
  $fromPath = Join-Path $src $m.From
  $toPath   = Join-Path $dst $m.To
  if (-not (Test-Path $fromPath)) {
    Write-Host "[$i/$total] SKIP (missing): $($m.From)"
    "SKIP    $($m.From)" | Add-Content $manifest
    continue
  }
  Write-Host "[$i/$total] MOVE: $($m.From)"
  New-Item -ItemType Directory -Path (Split-Path $toPath -Parent) -Force | Out-Null
  & robocopy $fromPath $toPath /MOVE /E /R:1 /W:1 /MT:16 /NFL /NDL /NP /XJ | Out-Null
  $code = $LASTEXITCODE
  if ($code -ge 8) {
    Write-Host "  FAILED (robocopy exit $code)"
    $failed += $m.From
    "FAILED [$code]  $($m.From)  ->  $($m.To)" | Add-Content $manifest
  } else {
    "MOVED  [$code]  $($m.From)  ->  $($m.To)" | Add-Content $manifest
    if ((Test-Path $fromPath) -and -not (Get-ChildItem $fromPath -Recurse -Force -ErrorAction SilentlyContinue)) {
      Remove-Item $fromPath -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

Write-Host ""
Write-Host "=== Summary ==="
Write-Host "Manifest: $manifest"
if ($failed.Count) {
  Write-Host "FAILED moves ($($failed.Count)):"
  $failed | ForEach-Object { Write-Host "  - $_" }
} else {
  Write-Host "All moves succeeded."
}
Write-Host ""
Write-Host "--- Workspace top-level after moves ---"
Get-ChildItem $src -Directory | Select-Object -ExpandProperty Name | Sort-Object
