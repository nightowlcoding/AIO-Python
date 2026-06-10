@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Python executable not found: %PYTHON_EXE%
  pause
  exit /b 1
)

echo Starting Inventory Control 3...
"%PYTHON_EXE%" "%~dp0inventory_control3_launcher.py"

endlocal
