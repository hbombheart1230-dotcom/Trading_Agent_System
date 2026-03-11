param(
  [string]$Root = "",
  [string]$Symbol = "",
  [string]$TickPipeline = "",
  [string]$SleepSec = "60",
  [string]$PidPath = "data\state\m13_live_loop.pid",
  [string]$LockPath = "data\state\m13_live_loop.lock",
  [string]$LockStaleSec = "1800",
  [string]$StdoutPath = "data\logs\m31_mock_session_stdout.log",
  [string]$StderrPath = "data\logs\m31_mock_session_stderr.log",
  [string]$ControlLogPath = "data\logs\m31_mock_session_control.log"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Root)) {
  $resolvedRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
} else {
  $resolvedRoot = (Resolve-Path $Root).Path
}

$pythonPath = Join-Path $resolvedRoot "venv\Scripts\python.exe"
$absPidPath = Join-Path $resolvedRoot $PidPath
$absLockPath = Join-Path $resolvedRoot $LockPath
$pidDir = Split-Path -Parent $absPidPath
$lockDir = Split-Path -Parent $absLockPath
$absStdoutPath = Join-Path $resolvedRoot $StdoutPath
$absStderrPath = Join-Path $resolvedRoot $StderrPath
$absControlLogPath = Join-Path $resolvedRoot $ControlLogPath
$stdoutDir = Split-Path -Parent $absStdoutPath
$stderrDir = Split-Path -Parent $absStderrPath
$controlDir = Split-Path -Parent $absControlLogPath

function Write-ControlLog {
  param([string]$Message)
  $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
  Add-Content -Path $absControlLogPath -Value "$ts start_mock_session $Message" -Encoding UTF8
}

if (!(Test-Path $pythonPath)) {
  Write-Error "python_not_found path=$pythonPath"
  exit 3
}

if (!(Test-Path $pidDir)) {
  New-Item -ItemType Directory -Path $pidDir -Force | Out-Null
}
if (!(Test-Path $lockDir)) {
  New-Item -ItemType Directory -Path $lockDir -Force | Out-Null
}
if (!(Test-Path $stdoutDir)) {
  New-Item -ItemType Directory -Path $stdoutDir -Force | Out-Null
}
if (!(Test-Path $stderrDir)) {
  New-Item -ItemType Directory -Path $stderrDir -Force | Out-Null
}
if (!(Test-Path $controlDir)) {
  New-Item -ItemType Directory -Path $controlDir -Force | Out-Null
}

$existingLoop = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
  $cmd = [string]$_.CommandLine
  (
    ($cmd -like "*scripts/run_m13_live_loop.py*") -or
    ($cmd -like "*-m scripts.run_m13_live_loop*")
  ) -and (
    ($cmd -like "*$absLockPath*") -or
    ($cmd -like "*$resolvedRoot*")
  )
} | Select-Object -First 1

if ($existingLoop) {
  $existingPid = [int]$existingLoop.ProcessId
  Set-Content -Path $absPidPath -Value ([string]$existingPid) -Encoding ASCII
  Write-ControlLog "already_running pid=$existingPid"
  Write-Output "already_running pid=$existingPid"
  exit 0
}

if (Test-Path $absPidPath) {
  $existingRaw = (Get-Content $absPidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
  $existingPid = 0
  if ($existingRaw) {
    $parsed = 0
    if ([int]::TryParse([string]$existingRaw, [ref]$parsed)) {
      $existingPid = $parsed
    }
  }
  if ($existingPid -gt 0) {
    $existingProc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($existingProc) {
      Write-ControlLog "already_running pid=$existingPid via_pid_file"
      Write-Output "already_running pid=$existingPid"
      exit 0
    }
  }
}

$resolvedTickPipeline = [string]$TickPipeline
if ([string]::IsNullOrWhiteSpace($resolvedTickPipeline)) {
  $resolvedTickPipeline = [string]$env:M13_TICK_PIPELINE
}
if ([string]::IsNullOrWhiteSpace($resolvedTickPipeline)) {
  $resolvedTickPipeline = "integrated_chain"
}
$resolvedTickPipeline = $resolvedTickPipeline.Trim().ToLowerInvariant()
if (($resolvedTickPipeline -ne "legacy_m10") -and ($resolvedTickPipeline -ne "integrated_chain")) {
  $resolvedTickPipeline = "integrated_chain"
}
if (($resolvedTickPipeline -eq "legacy_m10") -and [string]::IsNullOrWhiteSpace($Symbol)) {
  $resolvedTickPipeline = "integrated_chain"
  Write-ControlLog "tick_pipeline_fallback reason=missing_symbol selected=integrated_chain"
}

$args = @(
  "-m",
  "scripts.run_m13_live_loop",
  "--tick-pipeline", $resolvedTickPipeline,
  "--sleep-sec", $SleepSec,
  "--lock-path", $absLockPath,
  "--lock-stale-sec", $LockStaleSec
)
if ([string]::IsNullOrWhiteSpace($Symbol) -eq $false) {
  $args += @("--symbol", $Symbol)
}

$proc = Start-Process `
  -FilePath $pythonPath `
  -ArgumentList $args `
  -WorkingDirectory $resolvedRoot `
  -PassThru `
  -WindowStyle Hidden `
  -RedirectStandardOutput $absStdoutPath `
  -RedirectStandardError $absStderrPath

Set-Content -Path $absPidPath -Value ([string]$proc.Id) -Encoding ASCII
Start-Sleep -Seconds 2
$alive = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
if (!$alive) {
  Remove-Item -Path $absPidPath -Force -ErrorAction SilentlyContinue
  Write-ControlLog "start_failed process_exited_early root=$resolvedRoot lock=$absLockPath stdout=$absStdoutPath stderr=$absStderrPath"
  Write-Error "start_failed process_exited_early stdout=$absStdoutPath stderr=$absStderrPath"
  exit 4
}

Write-ControlLog "started pid=$($proc.Id) root=$resolvedRoot sleep_sec=$SleepSec lock=$absLockPath"
Write-Output "started pid=$($proc.Id) root=$resolvedRoot sleep_sec=$SleepSec lock=$absLockPath pid_path=$absPidPath stdout=$absStdoutPath stderr=$absStderrPath"
