@echo off
setlocal

set "ROOT=%~dp0"
set "GUI=%ROOT%Tools\toast_split_shift_gui.py"
set "KNOWNPY=C:\Users\arnol\.venvs\aio-python-ic3\Scripts\python.exe"
set "VENV=%ROOT%.venv\Scripts\python.exe"

if not exist "%GUI%" (
  echo GUI script not found:
  echo %GUI%
  exit /b 1
)

if exist "%KNOWNPY%" (
  "%KNOWNPY%" "%GUI%"
  exit /b %errorlevel%
)

if exist "%VENV%" (
  "%VENV%" "%GUI%"
  exit /b %errorlevel%
)

py "%GUI%"
exit /b %errorlevel%
