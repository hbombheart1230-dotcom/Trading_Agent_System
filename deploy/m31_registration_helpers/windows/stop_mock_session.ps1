param(
  [string]$Root = "C:\Trading_Agent_System",
  [string]$PidPath = "data\state\m13_live_loop.pid",
  [string]$ControlLogPath = "data\logs\m31_mock_session_control.log"
)

$ErrorActionPreference = "Stop"
$absPidPath = Join-Path $Root $PidPath
$absControlLogPath = Join-Path $Root $ControlLogPath
$controlDir = Split-Path -Parent $absControlLogPath
$stopped = 0

function Write-ControlLog {
  param([string]$Message)
  $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
  Add-Content -Path $absControlLogPath -Value "$ts stop_mock_session $Message" -Encoding UTF8
}

if (!(Test-Path $controlDir)) {
  New-Item -ItemType Directory -Path $controlDir -Force | Out-Null
}

function Stop-ById {
  param([int]$PidValue)
  if ($PidValue -le 0) {
    return $false
  }
  $proc = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
  if (!$proc) {
    return $false
  }
  Stop-Process -Id $PidValue -Force -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 200
  $remaining = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
  return ($null -eq $remaining)
}

if (Test-Path $absPidPath) {
  $raw = (Get-Content $absPidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
  $parsed = 0
  if ($raw -and [int]::TryParse([string]$raw, [ref]$parsed)) {
    if (Stop-ById -PidValue $parsed) {
      $stopped += 1
    }
  }
  Remove-Item -Path $absPidPath -Force -ErrorAction SilentlyContinue
}

$fallback = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
  ($_.CommandLine -like "*scripts/run_m13_live_loop.py*") -or
  ($_.CommandLine -like "*-m scripts.run_m13_live_loop*")
}

foreach ($p in $fallback) {
  $pidVal = [int]$p.ProcessId
  if (Stop-ById -PidValue $pidVal) {
    $stopped += 1
  }
}

Write-ControlLog "stopped_total=$stopped pid_path=$absPidPath"
Write-Output "stopped_total=$stopped pid_path=$absPidPath"
