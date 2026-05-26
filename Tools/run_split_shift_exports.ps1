param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot 'repeat_split_shift_exports.py'

if (-not (Test-Path $script)) {
    throw "Script not found: $script"
}

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$knownPython = 'C:\Users\arnol\.venvs\aio-python-ic3\Scripts\python.exe'

if (Test-Path $knownPython) {
    & $knownPython $script --delete-old @ExtraArgs
}
elseif (Test-Path $venvPython) {
    & $venvPython $script --delete-old @ExtraArgs
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py $script --delete-old @ExtraArgs
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $script --delete-old @ExtraArgs
}
else {
    throw 'No Python executable found (.venv, python, or py).'
}
