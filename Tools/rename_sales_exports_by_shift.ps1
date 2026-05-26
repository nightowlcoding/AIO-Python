param(
    [string]$CsvPath = "C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-05-19_Big House Burgers\Closed_Shifts_2026-05-19_Big_House_Burgers.csv",
    [string]$ExportDir = "C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-05-19_Big House Burgers",
    [string]$ReportDate = "2026-05-19",
    [switch]$Apply
)

function Get-ShiftLabel {
    param([datetime]$InDate)

    # Simplified rule:
    # Morning: shift starts at or before 12:00
    # Night: shift starts after 12:00 (12:01 PM+)
    $t = $InDate.TimeOfDay
    $morningCutoff = [timespan]::FromHours(12)    # 12:00

    if ($t -le $morningCutoff) { return "Morning" }
    return "Night"
}

if (-not (Test-Path $CsvPath)) {
    throw "CSV not found: $CsvPath"
}
if (-not (Test-Path $ExportDir)) {
    throw "Export folder not found: $ExportDir"
}

$rows = Import-Csv -Path $CsvPath

# Build per-employee shift labels from In Date.
$employeeShiftLabels = @{}
foreach ($row in $rows) {
    if (-not $row.Employee -or -not $row.'In Date') { continue }

    try {
        $inDate = [datetime]::Parse($row.'In Date')
    }
    catch {
        continue
    }

    $label = Get-ShiftLabel -InDate $inDate
    if (-not $employeeShiftLabels.ContainsKey($row.Employee)) {
        $employeeShiftLabels[$row.Employee] = New-Object System.Collections.Generic.List[string]
    }
    $employeeShiftLabels[$row.Employee].Add($label)
}

# One file currently exists per employee, so collapse multiple labels to one stable prefix.
# Priority keeps morning/night explicit when present, otherwise Day.
function Resolve-PrimaryLabel {
    param([string[]]$Labels)

    $unique = $Labels | Select-Object -Unique

    # Preserve rule meaning for employees with multiple shifts.
    # Example: Morning-Day or Morning-Night.
    $order = @('Morning', 'Day', 'Night')
    $ordered = foreach ($o in $order) {
        if ($unique -contains $o) { $o }
    }

    if ($ordered.Count -eq 0) { return 'Morning' }
    return ($ordered -join '-')
}

$xlsxFiles = Get-ChildItem -Path $ExportDir -Filter *.xlsx -File
$plan = New-Object System.Collections.Generic.List[object]

$employeeTokens = @{}
foreach ($emp in $employeeShiftLabels.Keys) {
    $employeeTokens[$emp] = ($emp -replace ' ', '_')
}

foreach ($f in $xlsxFiles) {
    # Handles both plain and previously-prefixed names ending with _YYYY-MM-DD.
    if ($f.BaseName -notmatch '^(?<token>.+?)_\d{4}-\d{2}-\d{2}$') {
        continue
    }

    $nameToken = $Matches['token']

    # Find which employee token appears inside the filename token.
    $matched = @()
    foreach ($emp in $employeeTokens.Keys) {
        $tok = $employeeTokens[$emp]
        if ($nameToken -imatch [regex]::Escape($tok)) {
            $matched += [pscustomobject]@{ Employee = $emp; Token = $tok; Len = $tok.Length }
        }
    }

    if ($matched.Count -eq 0) {
        continue
    }

    # Use longest token match for safety.
    $best = $matched | Sort-Object Len -Descending | Select-Object -First 1
    $employeeName = $best.Employee
    $baseEmployeeToken = $best.Token

    if (-not $employeeShiftLabels.ContainsKey($employeeName)) {
        continue
    }

    $primary = Resolve-PrimaryLabel -Labels $employeeShiftLabels[$employeeName].ToArray()
    $newBase = "{0}_{1}_{2}" -f $primary, $baseEmployeeToken, $ReportDate
    $newName = "$newBase$($f.Extension)"
    $newPath = Join-Path $ExportDir $newName

    $plan.Add([pscustomobject]@{
        Employee = $employeeName
        OldName  = $f.Name
        NewName  = $newName
        Labels   = (($employeeShiftLabels[$employeeName] | Select-Object -Unique) -join ', ')
        Action   = if ($f.Name -ieq $newName) { 'Skip (already named)' } elseif (Test-Path $newPath) { 'Skip (target exists)' } else { 'Rename' }
    })
}

$plan | Sort-Object Employee | Format-Table -AutoSize

if ($Apply) {
    foreach ($item in $plan | Where-Object { $_.Action -eq 'Rename' }) {
        Rename-Item -Path (Join-Path $ExportDir $item.OldName) -NewName $item.NewName -Force
    }
    Write-Host "Applied renames."
}
else {
    Write-Host "Preview mode only. Re-run with -Apply to rename files."
}
