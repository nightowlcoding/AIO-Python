# Non-destructive launcher for the main AIO apps.
# This script only starts selected apps and does not delete/move/rename anything.

Set-Location "c:\Users\arnol\OneDrive\Desktop\AIO-Python"

$python = ".\venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Python venv not found at $python" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "AIO Main App Launcher" -ForegroundColor Cyan
Write-Host "1) Product Mix Database"
Write-Host "2) Inventory Control 3"
Write-Host "3) Manager App"
Write-Host "4) Payroll Web Version"
Write-Host "5) Exit"
Write-Host ""

$choice = Read-Host "Choose an app number"

switch ($choice) {
    "1" {
        & $python "ProductMixRestaurantDB\app.py"
    }
    "2" {
        & $python "Restaurant Management\Inventory Control 3\inventory_control3_launcher.py"
    }
    "3" {
        & $python "Restaurant Management\Manager App\manager_app.py"
    }
    "4" {
        & $python "Restaurant Management\Payroll - WebVersion.py"
    }
    default {
        Write-Host "Exiting."
    }
}
