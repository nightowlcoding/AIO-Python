$target = "C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-05-19_Big House Burgers"
if (-not (Test-Path $target)) { New-Item -ItemType Directory -Path $target -Force | Out-Null }

$employees = @(
  "Emileigh Salinas",
  "Blaine Roberson",
  "Bryan Garcia",
  "Indira Garcia",
  "Kiara Mccoy",
  "Kaitlyn Esfahani",
  "Bailee Pena",
  "J'Elle Longoria",
  "Alyssa Rodriguez",
  "Marissa Alvarez",
  "Lariah Saenz",
  "Isabel Garcia"
)

$downloads = "C:\Users\arnol\Downloads"
$files = Get-ChildItem -Path $downloads -File | Where-Object {
  $_.Extension -in ".xlsx", ".xls", ".csv" -and
  $_.Name -notmatch "Daily_Log_Sales_Template_05_19_2026"
} | Sort-Object LastWriteTime

if (-not $files) {
  Write-Host "No spreadsheet files found in Downloads to rename."
  exit 0
}

$limit = [Math]::Min($files.Count, $employees.Count)
for ($i = 0; $i -lt $limit; $i++) {
  $emp = $employees[$i]
  $safe = ($emp -replace "[^A-Za-z0-9]+", "_").Trim('_')
  $ext = $files[$i].Extension
  $dest = Join-Path $target ("{0}_2026-05-19{1}" -f $safe, $ext)
  Move-Item -Path $files[$i].FullName -Destination $dest -Force
  Write-Host ("Renamed: {0} -> {1}" -f $files[$i].Name, [IO.Path]::GetFileName($dest))
}

Write-Host "Done."
Get-ChildItem -Path $target -File | Sort-Object Name | Select-Object Name, LastWriteTime
