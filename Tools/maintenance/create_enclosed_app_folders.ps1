param(
    [string]$RootPath = "C:\Users\arnol\OneDrive\Desktop\AIO-Python",
    [string]$EnclosureRootName = "AIO_Enclosed_Apps",
    [switch]$FullCopy
)

$ErrorActionPreference = "Stop"

function Normalize-Name {
    param([string]$Name)
    $safe = $Name -replace '[^a-zA-Z0-9._ -]', '_'
    return ($safe -replace '\s+', ' ').Trim()
}

function Should-SkipPath {
    param([string]$Path)

    $leaf = Split-Path $Path -Leaf
    if ($leaf -like 'AIO_*') { return $true }
    if ($Path -match '\\AIO_[^\\]+\\') { return $true }

    $segments = @(
        "\venv\", "\.git\", "\__pycache__\", "\build\", "\dist\",
        "\node_modules\", "\.mypy_cache\", "\.pytest_cache\",
        "\site-packages\", "\AIO_Enclosed_Apps\", "\AIO_Snapshots\"
    )
    foreach ($s in $segments) {
        if ($Path -like "*$s*") { return $true }
    }
    return $false
}

function New-EnclosureStructure {
    param([string]$Base)
    $dirs = @("source", "data", "config", "logs", "backups", "docs", "scripts")
    foreach ($d in $dirs) {
        $p = Join-Path $Base $d
        if (-not (Test-Path $p)) {
            New-Item -ItemType Directory -Path $p | Out-Null
        }
    }
}

$root = (Resolve-Path $RootPath).Path
$enclosureRoot = Join-Path $root $EnclosureRootName
if (-not (Test-Path $enclosureRoot)) {
    New-Item -ItemType Directory -Path $enclosureRoot | Out-Null
}

$created = @()

# 1) Top-level standalone python apps
$topPy = Get-ChildItem -Path $root -File -Filter *.py | Sort-Object Name
foreach ($py in $topPy) {
    $appName = Normalize-Name ($py.BaseName)
    $target = Join-Path $enclosureRoot $appName
    if (-not (Test-Path $target)) {
        New-Item -ItemType Directory -Path $target | Out-Null
    }
    New-EnclosureStructure -Base $target

    Copy-Item -Path $py.FullName -Destination (Join-Path $target "source\$($py.Name)") -Force

    $readme = Join-Path $target "START_HERE.txt"
    @(
        "App enclosure created from top-level Python file.",
        "",
        "Original source: $($py.FullName)",
        "Copied entry file: source\\$($py.Name)",
        "",
        "Folders created:",
        "- source",
        "- data",
        "- config",
        "- logs",
        "- backups",
        "- docs",
        "- scripts",
        "",
        "This enclosure is additive and does not delete or move any originals."
    ) | Set-Content -Path $readme -Encoding UTF8

    $created += [PSCustomObject]@{ Type = "top-level-py"; Name = $appName; Source = $py.FullName; Enclosure = $target }
}

# 2) Directory apps (contains app.py or run.py), excluding skipped paths
$entryFiles = Get-ChildItem -Path $root -Recurse -File -Include app.py,run.py -ErrorAction SilentlyContinue |
    Where-Object { -not (Should-SkipPath -Path $_.FullName) }

$appDirs = $entryFiles | ForEach-Object { $_.Directory.FullName } | Sort-Object -Unique

foreach ($dir in $appDirs) {
    if ($dir -eq $root) { continue }

    $relative = $dir.Substring($root.Length).TrimStart('\\')
    $appName = Normalize-Name ($relative -replace '\\', ' - ')
    $target = Join-Path $enclosureRoot $appName
    if (-not (Test-Path $target)) {
        New-Item -ItemType Directory -Path $target | Out-Null
    }
    New-EnclosureStructure -Base $target

    $sourceDest = Join-Path $target "source"
    if ($FullCopy) {
        # Copy full app directory contents into enclosure/source/app
        $destAppFolder = Join-Path $sourceDest ((Split-Path $dir -Leaf))
        if (-not (Test-Path $destAppFolder)) {
            New-Item -ItemType Directory -Path $destAppFolder | Out-Null
        }
        robocopy $dir $destAppFolder /E /NFL /NDL /NJH /NJS /NP /XD venv __pycache__ build dist node_modules .git | Out-Null
    }
    else {
        # Lightweight copy: only primary entry files + local requirements and readme docs
        $toCopy = @()
        $toCopy += Get-ChildItem -Path $dir -File -Filter app.py -ErrorAction SilentlyContinue
        $toCopy += Get-ChildItem -Path $dir -File -Filter run.py -ErrorAction SilentlyContinue
        $toCopy += Get-ChildItem -Path $dir -File -Filter requirements*.txt -ErrorAction SilentlyContinue
        $toCopy += Get-ChildItem -Path $dir -File -Filter README* -ErrorAction SilentlyContinue

        foreach ($f in ($toCopy | Sort-Object FullName -Unique)) {
            Copy-Item -Path $f.FullName -Destination (Join-Path $sourceDest $f.Name) -Force
        }
    }

    $copyMode = "LightweightCopy"
    if ($FullCopy) { $copyMode = "FullCopy" }

    $manifest = Join-Path $target "docs\manifest.txt"
    @(
        "App enclosure created from directory app.",
        "",
        "Original app directory: $dir",
        "Relative path: $relative",
        "Mode: $copyMode",
        "",
        "This enclosure is additive and does not delete or move any originals."
    ) | Set-Content -Path $manifest -Encoding UTF8

    $created += [PSCustomObject]@{ Type = "directory-app"; Name = $appName; Source = $dir; Enclosure = $target }
}

$indexPath = Join-Path $enclosureRoot "ENCLOSURE_INDEX.csv"
$created | Sort-Object Type, Name | Export-Csv -Path $indexPath -NoTypeInformation -Encoding UTF8

Write-Output "Enclosures created/updated: $($created.Count)"
Write-Output "Index: $indexPath"
