@echo off
REM Inventory Control System Startup Script for Windows

echo Starting Inventory Control System...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Please install Python 3 first.
    pause
    exit /b 1
)

REM Check if required packages are installed
echo Checking dependencies...
python -c "import flask, pandas" 2>nul
if errorlevel 1 (
    echo Installing required packages...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies. Please run: pip install flask pandas
        pause
        exit /b 1
    )
)

REM Check if CSV file exists
if not exist "Update - Sept 13th.csv" (
    echo Warning: Product CSV file not found!
    echo Please add 'Update - Sept 13th.csv' to this folder
    echo.
)

REM Start the application
echo All dependencies ready
echo Starting server...
echo.
python app.py

pause
