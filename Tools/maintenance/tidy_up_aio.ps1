param(
    [string]$RootPath = "C:\Users\arnol\OneDrive\Desktop\AIO-Python"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path $RootPath).Path
$tidyRoot = Join-Path $root "AIO_Tidy"
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$runRoot = Join-Path $tidyRoot "tidy_run_$stamp"

$loosePyDir = Join-Path $runRoot "Loose_Top_Level_Py"
$docsDir = Join-Path $runRoot "Top_Level_Docs"
$reportsDir = Join-Path $runRoot "Reports"

New-Item -ItemType Directory -Path $loosePyDir -Force | Out-Null
New-Item -ItemType Directory -Path $docsDir -Force | Out-Null
New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null

# Copy top-level Python files into tidy archive (copy only)
$topPy = Get-ChildItem -Path $root -File -Filter *.py | Sort-Object Name
foreach ($f in $topPy) {
    Copy-Item -Path $f.FullName -Destination (Join-Path $loosePyDir $f.Name) -Force
}

# Copy top-level docs into tidy archive
$topDocs = Get-ChildItem -Path $root -File -Include *.md,*.txt -ErrorAction SilentlyContinue | Sort-Object Name
foreach ($f in $topDocs) {
    Copy-Item -Path $f.FullName -Destination (Join-Path $docsDir $f.Name) -Force
}

# Build a quick app inventory report
$entries = @()
$entries += Get-ChildItem -Path $root -File -Filter *.py | ForEach-Object {
    [PSCustomObject]@{
        Type = "top-level-py"
        Name = $_.BaseName
        Path = $_.FullName
        LastWriteTime = $_.LastWriteTime
        Size = $_.Length
    }
}

$entryCandidates = Get-ChildItem -Path $root -Recurse -File -Include app.py,run.py -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -notlike "*\venv\*" -and
        $_.FullName -notlike "*\__pycache__\*" -and
        $_.FullName -notlike "*\node_modules\*" -and
        $_.FullName -notlike "*\build\*" -and
        $_.FullName -notlike "*\dist\*" -and
        $_.FullName -notlike "*\AIO_Enclosed_Apps\*" -and
        $_.FullName -notlike "*\AIO_Tidy\*"
    }

$dirs = $entryCandidates | ForEach-Object { $_.Directory.FullName } | Sort-Object -Unique
foreach ($d in $dirs) {
    $entries += [PSCustomObject]@{
        Type = "directory-app"
        Name = (Split-Path $d -Leaf)
        Path = $d
        LastWriteTime = (Get-Item $d).LastWriteTime
        Size = ""
    }
}

$inventoryCsv = Join-Path $reportsDir "app_inventory.csv"
$entries | Sort-Object Type, Name | Export-Csv -Path $inventoryCsv -NoTypeInformation -Encoding UTF8

$summary = Join-Path $runRoot "TIDY_SUMMARY.txt"
@(
    "AIO tidy run completed.",
    "",
    "Run folder: $runRoot",
    "Top-level Python files copied: $($topPy.Count)",
    "Top-level docs copied: $($topDocs.Count)",
    "App inventory rows: $($entries.Count)",
    "",
    "This process is copy-only. No files were deleted or moved."
) | Set-Content -Path $summary -Encoding UTF8

Write-Output "Tidy run: $runRoot"
Write-Output "Inventory: $inventoryCsv"
