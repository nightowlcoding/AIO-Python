param(
    [string]$RootPath = "C:\Users\arnol\OneDrive\Desktop\AIO-Python",
    [Parameter(Mandatory=$true)][string]$TargetPath,
    [ValidateSet("OneDrive","GoogleDrive","NAS","Other")][string]$TargetType = "Other"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path $RootPath).Path
if (-not (Test-Path $TargetPath)) {
    throw "Target path not found: $TargetPath"
}

$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$bundleRoot = Join-Path $TargetPath "AIO-Python_SyncBundle_$stamp"
New-Item -ItemType Directory -Path $bundleRoot -Force | Out-Null

# Always include latest snapshot zips + maintenance docs + enclosure index.
$snapshotDir = Join-Path $root "AIO_Snapshots"
$maintenanceDocs = Join-Path $root "docs\maintenance"
$enclosureIndex = Join-Path $root "AIO_Enclosed_Apps\ENCLOSURE_INDEX.csv"

if (Test-Path $snapshotDir) {
    $snapDest = Join-Path $bundleRoot "snapshots"
    New-Item -ItemType Directory -Path $snapDest -Force | Out-Null
    Get-ChildItem -Path $snapshotDir -File -Filter *.zip | Sort-Object LastWriteTime -Descending | Select-Object -First 7 |
        ForEach-Object { Copy-Item -Path $_.FullName -Destination (Join-Path $snapDest $_.Name) -Force }
}

if (Test-Path $maintenanceDocs) {
    $docDest = Join-Path $bundleRoot "maintenance_docs"
    New-Item -ItemType Directory -Path $docDest -Force | Out-Null
    Copy-Item -Path (Join-Path $maintenanceDocs '*') -Destination $docDest -Recurse -Force
}

if (Test-Path $enclosureIndex) {
    Copy-Item -Path $enclosureIndex -Destination (Join-Path $bundleRoot "ENCLOSURE_INDEX.csv") -Force
}

$readme = Join-Path $bundleRoot "SYNC_BUNDLE_README.txt"
@(
    "AIO sync bundle created.",
    "Target type: $TargetType",
    "Created: $stamp",
    "Source root: $root",
    "",
    "Contents include:",
    "- Recent snapshots",
    "- Maintenance docs",
    "- Enclosure index",
    "",
    "This is a copy-only export bundle."
) | Set-Content -Path $readme -Encoding UTF8

Write-Output "Sync bundle created: $bundleRoot"
