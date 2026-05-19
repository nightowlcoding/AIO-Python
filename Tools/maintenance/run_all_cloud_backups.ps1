param(
    [string]$RootPath = "C:\Users\arnol\OneDrive\Desktop\AIO-Python",
    [string]$OneDriveTarget = "C:\Users\arnol\OneDrive",
    [string]$GoogleDriveTarget = "G:\My Drive"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path $RootPath).Path
$maintenanceDir = Join-Path $root "Tools\maintenance"
$logDir = Join-Path $maintenanceDir "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logPath = Join-Path $logDir "cloud_backup_$stamp.log"

function Write-Log {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Output $line
    Add-Content -Path $logPath -Value $line
}

Write-Log "Starting cloud backup run"
Write-Log "RootPath=$root"

$createSnapshot = Join-Path $maintenanceDir "create_aio_snapshot.ps1"
$syncScript = Join-Path $maintenanceDir "sync_to_storage_target.ps1"

if (-not (Test-Path $createSnapshot)) { throw "Missing snapshot script: $createSnapshot" }
if (-not (Test-Path $syncScript)) { throw "Missing sync script: $syncScript" }

try {
    Write-Log "Creating fresh snapshot"
    & powershell -ExecutionPolicy Bypass -File $createSnapshot -RootPath $root | ForEach-Object { Write-Log $_ }

    if (Test-Path $OneDriveTarget) {
        Write-Log "Exporting OneDrive sync bundle to $OneDriveTarget"
        & powershell -ExecutionPolicy Bypass -File $syncScript -RootPath $root -TargetPath $OneDriveTarget -TargetType OneDrive | ForEach-Object { Write-Log $_ }
    }
    else {
        Write-Log "Skipping OneDrive: target not found -> $OneDriveTarget"
    }

    if (Test-Path $GoogleDriveTarget) {
        Write-Log "Exporting Google Drive sync bundle to $GoogleDriveTarget"
        & powershell -ExecutionPolicy Bypass -File $syncScript -RootPath $root -TargetPath $GoogleDriveTarget -TargetType GoogleDrive | ForEach-Object { Write-Log $_ }
    }
    else {
        Write-Log "Skipping Google Drive: target not found -> $GoogleDriveTarget"
    }

    Write-Log "Cloud backup run completed successfully"
}
catch {
    Write-Log "Cloud backup run failed: $($_.Exception.Message)"
    throw
}
