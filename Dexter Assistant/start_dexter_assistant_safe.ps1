param(
    [int]$Port = 5080,
    [string]$AppPath = "",
    [switch]$OpenPortal
)

$ErrorActionPreference = "Stop"

if (-not $AppPath) {
    $AppPath = Join-Path $PSScriptRoot "dexter_assistant.py"
}

if (-not (Test-Path -Path $AppPath -PathType Leaf)) {
    throw "Dexter app entrypoint not found: $AppPath"
}

$appDir = Split-Path -Path $AppPath -Parent
$appPathForMatch = [Regex]::Escape((Resolve-Path $AppPath).Path)

function Resolve-PythonCommand {
    $candidates = @(
        (Join-Path $PSScriptRoot "..\..\.venv\Scripts\python.exe"),
        (Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"),
        (Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"),
        (Join-Path $PSScriptRoot "ProductMixRestaurantDB\.venv\Scripts\python.exe"),
        "C:\Users\arnol\.venvs\aio-python-ic3\Scripts\python.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -Path $candidate -PathType Leaf) {
            return @{ FilePath = (Resolve-Path $candidate).Path; Arguments = @() }
        }
    }

    return @{ FilePath = "py"; Arguments = @("-3") }
}

function Stop-StaleDexterProcesses {
    $pythonLike = @("python.exe", "pythonw.exe")
    $stale = @()

    foreach ($name in $pythonLike) {
        $procs = Get-CimInstance Win32_Process -Filter "Name = '$name'" -ErrorAction SilentlyContinue
        foreach ($p in ($procs | Where-Object { $_.CommandLine -and $_.CommandLine -match "dexter_assistant\.py" })) {
            $stale += $p
        }
    }

    $stale = $stale | Sort-Object ProcessId -Unique
    if (-not $stale) {
        Write-Host "[safe-start] No stale dexter_assistant processes found."
        return
    }

    foreach ($proc in $stale) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "[safe-start] Stopped stale process PID $($proc.ProcessId)."
        } catch {
            Write-Warning "[safe-start] Failed to stop PID $($proc.ProcessId): $($_.Exception.Message)"
        }
    }
}

function Clear-ListeningPort {
    param([int]$LocalPort)

    $listeners = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique

    if (-not $listeners) {
        Write-Host "[safe-start] Port $LocalPort is free."
        return
    }

    foreach ($pid in $listeners) {
        try {
            $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
            $name = if ($proc) { $proc.ProcessName } else { "unknown" }
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Host "[safe-start] Stopped PID $pid ($name) on port $LocalPort."
        } catch {
            Write-Warning "[safe-start] Could not stop PID $pid on port ${LocalPort}: $($_.Exception.Message)"
        }
    }
}

function Wait-ForPort {
    param(
        [int]$LocalPort,
        [int]$TimeoutSeconds = 20
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $listener = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
        if ($listener) {
            return $true
        }
        Start-Sleep -Milliseconds 400
    }

    return $false
}

Write-Host "[safe-start] Preparing Dexter Assistant..."
Stop-StaleDexterProcesses
Clear-ListeningPort -LocalPort $Port

$python = Resolve-PythonCommand
$pythonExe = $python.FilePath
$baseArgs = @($python.Arguments)

Write-Host "[safe-start] Using Python: $pythonExe"
Write-Host "[safe-start] Working directory: $appDir"
Write-Host "[safe-start] Starting Dexter Assistant on port $Port..."

$allArgs = @()
$allArgs += $baseArgs
$allArgs += @('"' + $AppPath + '"')

$started = Start-Process -FilePath $pythonExe -ArgumentList $allArgs -WorkingDirectory $appDir -PassThru

if (Wait-ForPort -LocalPort $Port -TimeoutSeconds 20) {
    Write-Host "[safe-start] Dexter Assistant is live at http://127.0.0.1:$Port/portal?hub=1"
    if ($OpenPortal) {
        Start-Process "http://127.0.0.1:$Port/portal?hub=1"
    }
} else {
    Write-Warning "[safe-start] App process started (PID $($started.Id)) but port $Port was not ready within timeout."
    Write-Warning "[safe-start] Check logs by running dexter_assistant.py directly if needed."
}
