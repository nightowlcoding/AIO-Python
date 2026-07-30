@echo off
setlocal
cd /d "%~dp0"

set "SAFE_SCRIPT=%~dp0start_dexter_assistant_safe.ps1"

if exist "%SAFE_SCRIPT%" (
	echo Running Dexter Assistant safe launcher...
	powershell -NoProfile -ExecutionPolicy Bypass -File "%SAFE_SCRIPT%" %*
	if errorlevel 1 (
		echo Safe launcher failed. Fix that error instead of falling back to an inconsistent direct start.
		exit /b %errorlevel%
	)
	goto :eof
)

set "PYTHON_ARGS="
set "PYTHON_EXE=C:\Users\arnol\.venvs\aio-python-ic3\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0..\..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0..\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0ProductMixRestaurantDB\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
	set "PYTHON_EXE=py"
	set "PYTHON_ARGS=-3"
)

echo Starting Dexter Assistant front door...
"%PYTHON_EXE%" %PYTHON_ARGS% "%~dp0dexter_assistant.py"

endlocal
