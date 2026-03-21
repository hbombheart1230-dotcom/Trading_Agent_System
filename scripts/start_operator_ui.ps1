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

Write-Warning "[DEPRECATED-SOFT] Operator UI launch is manual check only."
Write-Warning "[DEPRECATED-SOFT] Current priority is report/trade artifact quality. UI is intentionally deferred."

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

$url = "http://$ListenHost`:$Port/"
$healthUrl = "http://$ListenHost`:$Port/healthz"
$health = $null
$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 750
    try {
        $health = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
    } catch {
        $health = $null
    }
} while (-not $health -and (Get-Date) -lt $deadline)

if (-not $health) {
    $stillRunning = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    if ($stillRunning) {
        Write-Output ("PID=" + $proc.Id)
        Write-Output ("URL=" + $url)
        Write-Output ("HEALTH=pending")
        if ($OpenBrowser) {
            Start-Process $url | Out-Null
        }
        return
    }
    throw "operator UI health check timed out: $healthUrl"
}

Write-Output ("PID=" + $proc.Id)
Write-Output ("URL=" + $url)
Write-Output ("HEALTH=" + $health.Content)

if ($OpenBrowser) {
    Start-Process $url | Out-Null
}
