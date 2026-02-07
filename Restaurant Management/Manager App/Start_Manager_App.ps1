# Manager App Launcher (PowerShell)
# This script activates the virtual environment and starts the Manager App

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Manager App - Starting..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to the AIO Programs folder
Set-Location "C:\Users\arnol\OneDrive\Desktop\AIO Programs"

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& ".venv\Scripts\Activate.ps1"

# Navigate to Manager App folder
Set-Location "AIO Python\Restaurant Management\Manager App"

# Start the application
Write-Host ""
Write-Host "Starting Flask server..." -ForegroundColor Green
Write-Host ""
Write-Host "Once started, open your browser to: " -NoNewline
Write-Host "http://127.0.0.1:8000" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

try {
    python manager_app.py
} catch {
    Write-Host ""
    Write-Host "ERROR: Application failed to start!" -ForegroundColor Red
    Write-Host "Check the error messages above." -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
}
