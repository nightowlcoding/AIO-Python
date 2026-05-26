param(
    [Parameter(Mandatory = $true)]
    [string]$SourceCsv,

    [Parameter(Mandatory = $true)]
    [string]$OutputCsv
)

if (-not (Test-Path $SourceCsv)) {
    throw "Source CSV not found: $SourceCsv"
}

$rows = Import-Csv $SourceCsv
$multiShiftEmployees = $rows |
    Group-Object Employee |
    Where-Object { $_.Count -gt 1 } |
    Select-Object -ExpandProperty Name

$formats = @(
    'M/d/yy h:mm tt',
    'M/d/yy h:mm:ss tt',
    'M/d/yyyy h:mm tt',
    'M/d/yyyy h:mm:ss tt'
)
$culture = [System.Globalization.CultureInfo]::GetCultureInfo('en-US')

$out = New-Object System.Collections.Generic.List[object]

foreach ($row in ($rows | Where-Object { $_.Employee -in $multiShiftEmployees })) {
    try {
        $inDate = [datetime]::Parse($row.'In Date', $culture)
        $endDate = [datetime]::Parse($row.'Shift Closed Date', $culture)
    }
    catch {
        continue
    }

    $out.Add([pscustomobject]@{
        Employee          = $row.Employee
        StartDateTime     = $row.'In Date'
        EndDateTime       = $row.'Shift Closed Date'
        StartTimeForToast = $inDate.ToString('h:mm tt')
        EndTimeForToast   = $endDate.ToString('h:mm tt')
        StartTime24       = $inDate.ToString('HH:mm')
        EndTime24         = $endDate.ToString('HH:mm')
        StartHour12       = $inDate.ToString('%h')
        StartMinute       = $inDate.ToString('mm')
        StartMeridiem     = $inDate.ToString('tt')
        EndHour12         = $endDate.ToString('%h')
        EndMinute         = $endDate.ToString('mm')
        EndMeridiem       = $endDate.ToString('tt')
        ShiftLabel        = if ($inDate.TimeOfDay -le [timespan]::FromHours(12)) { 'Morning' } else { 'Night' }
    })
}

$out = $out | Sort-Object Employee, { [datetime]::Parse($_.StartDateTime, $culture) }

$out | Export-Csv -Path $OutputCsv -NoTypeInformation

Write-Host "Created: $OutputCsv"
Write-Host "Rows: $($out.Count)"
