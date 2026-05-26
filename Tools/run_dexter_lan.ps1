# Run the Dexter launcher bound to all interfaces so phones / tablets on the
# same Wi-Fi can reach it. Open the URL printed below on your phone.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root "venv\Scripts\python.exe"
$app = Join-Path $root "Dexter Assistant\dexter_assistant.py"

# Pick the first IPv4 LAN address (Wi-Fi or Ethernet).
$ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
       Where-Object { $_.IPAddress -match '^(192\.168|10\.|172\.)' } |
       Select-Object -First 1).IPAddress
if (-not $ip) { $ip = "<your-LAN-IP>" }

Write-Host ""
Write-Host "  Dexter Launcher — LAN mode" -ForegroundColor Cyan
Write-Host "  ---------------------------" -ForegroundColor Cyan
Write-Host "  On this PC : http://127.0.0.1:5080"
Write-Host "  On phone   : http://${ip}:5080" -ForegroundColor Yellow
Write-Host ""
Write-Host "  If the phone can't connect, run (as admin, one time):"
Write-Host "    New-NetFirewallRule -DisplayName 'Dexter Launcher 5080' \\"
Write-Host "      -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5080"
Write-Host ""

$env:DEXTER_HOST = "0.0.0.0"
$env:DEXTER_PORT = "5080"
& $py $app
