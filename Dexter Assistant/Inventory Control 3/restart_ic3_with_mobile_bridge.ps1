# Restart Inventory Control 3 with Mobile Sync Bridge
# PowerShell version for easy restart

$VenvPath = "c:\Users\arnol\OneDrive\Desktop\AIO-Python\venv"
$IC3Path = "c:\Users\arnol\OneDrive\Desktop\AIO-Python\Dexter Assistant\Inventory Control 3"
$AppFile = "$IC3Path\app.py"
$Python = "$VenvPath\Scripts\python.exe"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Inventory Control 3 - Restart Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python exists
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Python executable not found at:" -ForegroundColor Red
    Write-Host $Python -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Kill any existing python processes (be careful!)
Write-Host "[*] Stopping existing IC3 processes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "[*] Starting Inventory Control 3..." -ForegroundColor Yellow
Write-Host "[*] App: $AppFile"
Write-Host "[*] Python: $Python"
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " IC3 is starting..." -ForegroundColor Green
Write-Host " Main App:       http://127.0.0.1:5003" -ForegroundColor Green
Write-Host " Mobile Sync:    http://127.0.0.1:5004" -ForegroundColor Green
Write-Host " Mobile UI:      http://127.0.0.1:5004/" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Start the app
Set-Location $IC3Path
& $Python $AppFile
