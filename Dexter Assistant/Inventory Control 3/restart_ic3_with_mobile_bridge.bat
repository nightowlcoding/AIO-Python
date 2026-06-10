@echo off
REM Restart Inventory Control 3 with Mobile Sync Bridge
REM This script stops the running IC3 process and restarts it

setlocal enabledelayedexpansion

set "VENV_PATH=c:\Users\arnol\OneDrive\Desktop\AIO-Python\venv"
set "IC3_PATH=c:\Users\arnol\OneDrive\Desktop\AIO-Python\Dexter Assistant\Inventory Control 3"
set "APP_FILE=%IC3_PATH%\app.py"
set "PYTHON=%VENV_PATH%\Scripts\python.exe"

echo.
echo ========================================
echo  Inventory Control 3 - Restart Script
echo ========================================
echo.

REM Check if Python exists
if not exist "%PYTHON%" (
    echo ERROR: Python executable not found at:
    echo %PYTHON%
    pause
    exit /b 1
)

REM Kill any existing IC3 processes
echo [*] Stopping existing IC3 processes...
for /f "tokens=2" %%A in ('tasklist ^| findstr /I "python.exe"') do (
    taskkill /PID %%A /F 2>nul
)

timeout /t 2 /nobreak

echo [*] Starting Inventory Control 3...
echo [*] App: %APP_FILE%
echo [*] Python: %PYTHON%
echo.
echo ========================================
echo  IC3 is starting...
echo  Main App:       http://127.0.0.1:5003
echo  Mobile Sync:    http://127.0.0.1:5004
echo  Mobile UI:      http://127.0.0.1:5004/
echo ========================================
echo.

REM Start the app
cd /d "%IC3_PATH%"
"%PYTHON%" "%APP_FILE%"

pause
