param(
    [string]$SourceRoot = "c:\Users\arnol\Coding Files\AIO-Python\Dexter Assistant",
    [string]$NasRoot = "\\RAMIREZCLANNAS\personal_folder\DexterStorage",
    [switch]$WhatIf,
    [int]$RetentionDays = 15
)

$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$targetRoot = Join-Path $NasRoot "dexterassist_backups\snapshot_$timestamp"

if (-not (Test-Path $NasRoot)) {
    throw "NAS path is not reachable: $NasRoot"
}

New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null

$filesToCopy = @(
    "dexter_assistant_rbac.db",
    "dexter_assistant_users.json",
    "Manager App\manager_app.db"
)

$dirsToCopy = @(
    "Manager App\company_data",
    "Inventory Control 3\data",
    "ProductMixRestaurantDB",
    "inventory_data",
    "daily_logs",
    "uploads",
    "OrderInvoices",
    "reports"
)

$manifest = [ordered]@{
    created_at = (Get-Date).ToString("o")
    source_root = $SourceRoot
    target_root = $targetRoot
    files = @()
    directories = @()
}

foreach ($rel in $filesToCopy) {
    $src = Join-Path $SourceRoot $rel
    if (Test-Path $src) {
        $dst = Join-Path $targetRoot $rel
        New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
        if (-not $WhatIf) {
            Copy-Item -Path $src -Destination $dst -Force
        }

        $entry = [ordered]@{
            path = $rel
            exists = $true
        }
        if (-not $WhatIf) {
            $hash = Get-FileHash -Path $dst -Algorithm SHA256
            $entry.sha256 = $hash.Hash
            $entry.bytes = (Get-Item $dst).Length
        }
        $manifest.files += $entry
    }
    else {
        $manifest.files += [ordered]@{ path = $rel; exists = $false }
    }
}

foreach ($rel in $dirsToCopy) {
    $src = Join-Path $SourceRoot $rel
    if (Test-Path $src) {
        $dst = Join-Path $targetRoot $rel
        if (-not $WhatIf) {
            New-Item -ItemType Directory -Path $dst -Force | Out-Null
            robocopy $src $dst /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
        }

        $fileCount = if (-not $WhatIf) { (Get-ChildItem -Path $dst -Recurse -File | Measure-Object).Count } else { -1 }
        $manifest.directories += [ordered]@{
            path = $rel
            exists = $true
            file_count = $fileCount
        }
    }
    else {
        $manifest.directories += [ordered]@{ path = $rel; exists = $false; file_count = 0 }
    }
}

$manifestPath = Join-Path $targetRoot "manifest.json"
if (-not $WhatIf) {
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -Path $manifestPath -Encoding UTF8

    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    Get-ChildItem -Path (Join-Path $NasRoot "dexterassist_backups") -Directory -Filter "snapshot_*" | ForEach-Object {
        if ($_.LastWriteTime -lt $cutoff) {
            Remove-Item -Path $_.FullName -Recurse -Force
        }
    }

    $gdriveCredentials = $env:DEXTER_GDRIVE_SERVICE_ACCOUNT_FILE
    $gdriveFolderId = $env:DEXTER_GDRIVE_FOLDER_ID
    $gdriveScript = Join-Path $PSScriptRoot "backup_to_google_drive.py"
    if ($gdriveCredentials -and (Test-Path $gdriveCredentials) -and (Test-Path $gdriveScript)) {
        $pythonCmd = $null
        try {
            $pythonCmd = (Get-Command python -ErrorAction Stop).Source
        }
        catch {
            try {
                $pythonCmd = (Get-Command py -ErrorAction Stop).Source
            }
            catch {
                $pythonCmd = $null
            }
        }

        if ($pythonCmd) {
            try {
                $args = @(
                    $gdriveScript,
                    "--source-dir", $targetRoot,
                    "--retention-days", $RetentionDays
                )
                if ($gdriveFolderId) {
                    $args += @("--folder-id", $gdriveFolderId)
                }
                & $pythonCmd @args | Out-Null
                Write-Host "Google Drive backup complete"
            }
            catch {
                Write-Warning "Google Drive backup failed but NAS backup succeeded: $($_.Exception.Message)"
            }
        }
    }
}

Write-Host "Backup complete"
Write-Host "Target: $targetRoot"
Write-Host "Manifest: $manifestPath"
