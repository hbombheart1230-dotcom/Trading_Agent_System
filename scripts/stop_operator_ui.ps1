param(
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"

Write-Warning "[DEPRECATED-SOFT] Operator UI runtime is deferred in current workflow."
Write-Warning "[DEPRECATED-SOFT] Keep using report/trades artifacts as the primary output surface."

$matches = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -like "python*" -and
        $_.CommandLine -like "*run_operator_ui.py*" -and
        $_.CommandLine -like "*--port $Port*"
    }

foreach ($proc in $matches) {
    try {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        Write-Output ("STOPPED=" + $proc.ProcessId)
    } catch {
        Write-Output ("FAILED=" + $proc.ProcessId)
    }
}

if (-not $matches) {
    Write-Output "STOPPED=0"
}
