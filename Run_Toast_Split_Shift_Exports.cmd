@echo off
setlocal

set "SCRIPT=%~dp0Tools\run_split_shift_exports.ps1"

if not exist "%SCRIPT%" (
  echo Could not find launcher script:
  echo %SCRIPT%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %errorlevel%
