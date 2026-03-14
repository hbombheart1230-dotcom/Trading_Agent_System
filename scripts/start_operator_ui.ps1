param(
    [string]$EnvPath = ".env",
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8010,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "venv\Scripts\python.exe"
$script = Join-Path $root "scripts\run_operator_ui.py"

if (-not (Test-Path $python)) {
    throw "python not found: $python"
}

if (-not (Test-Path $script)) {
    throw "script not found: $script"
}

$existing = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -like "python*" -and
        $_.CommandLine -like "*run_operator_ui.py*" -and
        $_.CommandLine -like "*--port $Port*"
    }

foreach ($proc in $existing) {
    try {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
    } catch {
    }
}

$args = @(
    $script,
    "--env-path", $EnvPath,
    "--host", $ListenHost,
    "--port", "$Port"
)

$proc = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $root -PassThru
Start-Sleep -Seconds 3

$url = "http://$ListenHost`:$Port/"
$healthUrl = "http://$ListenHost`:$Port/healthz"
$health = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5

Write-Output ("PID=" + $proc.Id)
Write-Output ("URL=" + $url)
Write-Output ("HEALTH=" + $health.Content)

if ($OpenBrowser) {
    Start-Process $url | Out-Null
}
