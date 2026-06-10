@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_ARGS="
set "PYTHON_EXE=C:\Users\arnol\.venvs\aio-python-ic3\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0..\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%~dp0ProductMixRestaurantDB\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
	set "PYTHON_EXE=py"
	set "PYTHON_ARGS=-3"
)

echo Starting Dexter Assistant front door...
"%PYTHON_EXE%" %PYTHON_ARGS% "%~dp0dexter_assistant.py"

endlocal
