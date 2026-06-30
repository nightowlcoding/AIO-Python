param(
    [string]$RepoRoot = "c:\Users\arnol\Coding Files\AIO-Python",
    [switch]$SkipSnapshots
)

$ErrorActionPreference = "Stop"

$dexterRoot = Join-Path $RepoRoot "Dexter Assistant"
$backupScript = Join-Path $dexterRoot "deploy\backup_to_nas.ps1"
$integrityScript = Join-Path $dexterRoot "deploy\data_guard.py"
$preflightScript = Join-Path $dexterRoot "deploy\release_preflight.py"

if (-not (Test-Path $preflightScript)) {
    throw "Missing preflight script: $preflightScript"
}

if (-not $SkipSnapshots) {
    if (-not (Test-Path $backupScript)) {
        throw "Missing backup script: $backupScript"
    }
    if (-not (Test-Path $integrityScript)) {
        throw "Missing integrity script: $integrityScript"
    }

    Write-Host "[release-guard] Running NAS snapshot..."
    & $backupScript

    Write-Host "[release-guard] Creating local integrity snapshot..."
    & python $integrityScript --source-root $dexterRoot snapshot
}

Write-Host "[release-guard] Running release preflight checks..."
& python $preflightScript --repo-root $RepoRoot

Write-Host "[release-guard] PASS: Safe to commit/push code-only changes."
