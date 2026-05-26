<#
  sync_dexter_ui.ps1
  Mirrors the canonical Dexter UI source (Tools\dexter_ui) into each
  Flask app's static\dexter-ui\ folder.

  Usage:
    powershell -ExecutionPolicy Bypass -File Tools\dexter_ui\sync_dexter_ui.ps1
#>

$ErrorActionPreference = 'Stop'

# sync_dexter_ui.ps1 lives at <repo>\Tools\dexter_ui\sync_dexter_ui.ps1
# Walk up three levels to get the workspace root.
$source = Split-Path -Parent $PSCommandPath                 # ...\Tools\dexter_ui
$root   = Split-Path -Parent (Split-Path -Parent $source)   # workspace root

# Targets: (app-relative path under Dexter Assistant) -> required
$targets = @(
    @{ Name = 'ProductMixRestaurantDB'; Path = 'Dexter Assistant\ProductMixRestaurantDB\static\dexter-ui' },
    @{ Name = 'Manager App';            Path = 'Dexter Assistant\Manager App\static\dexter-ui' },
    @{ Name = 'Inventory Control 3';    Path = 'Dexter Assistant\Inventory Control 3\dexter-ui' },
    @{ Name = 'Dexter Assistant';       Path = 'Dexter Assistant\dexter-ui' }
)

# Files to copy from the source (canonical names only, no PowerShell scripts or generators)
$files = @('tokens.css', 'components.css', 'app-shell.css', 'theme.js')

foreach ($t in $targets) {
    $destBase = Join-Path $root $t.Path
    $destBrand = Join-Path $destBase 'brand'
    if (-not (Test-Path $destBase))  { New-Item -ItemType Directory -Path $destBase  -Force | Out-Null }
    if (-not (Test-Path $destBrand)) { New-Item -ItemType Directory -Path $destBrand -Force | Out-Null }

    foreach ($f in $files) {
        $src = Join-Path $source $f
        if (Test-Path $src) {
            Copy-Item -Force -Path $src -Destination (Join-Path $destBase $f)
        }
    }

    # Brand assets
    $brandSrc = Join-Path $source 'brand'
    if (Test-Path $brandSrc) {
        Copy-Item -Force -Recurse -Path (Join-Path $brandSrc '*') -Destination $destBrand
    }

    Write-Host ("[sync] {0,-22} <- {1}" -f $t.Name, $destBase)
}

Write-Host ""
Write-Host "[sync] dexter-ui synced to $($targets.Count) apps."
