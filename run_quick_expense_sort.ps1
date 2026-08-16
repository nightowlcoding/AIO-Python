$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $base

$python = "c:/Users/arnol/Coding Files/.venv/Scripts/python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Python not found at $python"
}

& $python ".\quick_expense_recurring.py"
