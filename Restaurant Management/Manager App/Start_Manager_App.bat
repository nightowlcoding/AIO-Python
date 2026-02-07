@echo off
REM Manager App Launcher
REM This script activates the virtual environment and starts the Manager App

echo =========================================
echo   Manager App - Starting...
echo =========================================
echo.

REM Navigate to the AIO Programs folder
cd /d "C:\Users\arnol\OneDrive\Desktop\AIO Programs"

REM Activate virtual environment
call ".venv\Scripts\activate.bat"

REM Navigate to Manager App folder
cd "AIO Python\Restaurant Management\Manager App"

REM Start the application
echo Starting Flask server...
echo.
echo Once started, open your browser to: http://127.0.0.1:8000
echo.
echo Press Ctrl+C to stop the server
echo.
python manager_app.py

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo ERROR: Application failed to start!
    echo Check the error messages above.
    echo.
    pause
)
