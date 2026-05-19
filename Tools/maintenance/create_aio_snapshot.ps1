param(
    [string]$RootPath = "C:\Users\arnol\OneDrive\Desktop\AIO-Python",
    [string]$OutputDirName = "AIO_Snapshots"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path $RootPath).Path
$outDir = Join-Path $root $OutputDirName
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir | Out-Null
}

$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$zipName = "AIO-Python_snapshot_$stamp.zip"
$zipPath = Join-Path $outDir $zipName

$tempCopy = Join-Path $env:TEMP "AIO-Python_snapshot_$stamp"
if (Test-Path $tempCopy) {
    Remove-Item -Path $tempCopy -Recurse -Force
}

New-Item -ItemType Directory -Path $tempCopy | Out-Null

# Copy everything except large/generated folders to speed up snapshots.
# Exclude maintenance output trees so automated snapshots stay compact and avoid deep-path archive errors.
robocopy $root $tempCopy /E /NFL /NDL /NJH /NJS /NP /XD venv __pycache__ .git build dist node_modules AIO_Snapshots AIO_Enclosed_Apps AIO_Consolidated_Full AIO_Consolidated_Clean AIO_Tidy | Out-Null

if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}
Compress-Archive -Path (Join-Path $tempCopy '*') -DestinationPath $zipPath -CompressionLevel Fastest

Remove-Item -Path $tempCopy -Recurse -Force

Write-Output "Snapshot created: $zipPath"
