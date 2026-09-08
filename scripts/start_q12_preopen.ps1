$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$day = Get-Date -Format 'yyyy-MM-dd'
$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python' -and
    $_.CommandLine -match [regex]::Escape($root) -and
    $_.CommandLine -match 'run_baseline_btc_woori_tech.py' -and
    $_.CommandLine -match "--day\s+$day"
}
if ($existing) { Write-Output 'q12_preopen=already_running'; exit 0 }
$logs = Join-Path $root 'reports/runtime'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$process = Start-Process -FilePath (Join-Path $root 'venv/Scripts/python.exe') `
    -ArgumentList @('scripts/run_baseline_btc_woori_tech.py', '--day', $day,
        '--reports-root', 'reports', '--state-path', 'data/state.json', '--loop', '--interval-sec', '300') `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "q12_preopen_$stamp.out.log") `
    -RedirectStandardError (Join-Path $logs "q12_preopen_$stamp.err.log") -PassThru
Write-Output "q12_preopen_pid=$($process.Id)"
