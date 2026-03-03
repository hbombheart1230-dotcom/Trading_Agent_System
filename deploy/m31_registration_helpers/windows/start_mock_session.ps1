param(
  [string]$Root = "C:\Trading_Agent_System",
  [string]$Symbol = "",
  [string]$SleepSec = "60",
  [string]$PidPath = "data\state\m13_live_loop.pid",
  [string]$StdoutPath = "data\logs\m31_mock_session_stdout.log",
  [string]$StderrPath = "data\logs\m31_mock_session_stderr.log",
  [string]$ControlLogPath = "data\logs\m31_mock_session_control.log"
)

$ErrorActionPreference = "Stop"

$pythonPath = Join-Path $Root "venv\Scripts\python.exe"
$absPidPath = Join-Path $Root $PidPath
$pidDir = Split-Path -Parent $absPidPath
$absStdoutPath = Join-Path $Root $StdoutPath
$absStderrPath = Join-Path $Root $StderrPath
$absControlLogPath = Join-Path $Root $ControlLogPath
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
  ($_.CommandLine -like "*scripts/run_m13_live_loop.py*") -or
  ($_.CommandLine -like "*-m scripts.run_m13_live_loop*")
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

$args = @(
  "-m",
  "scripts.run_m13_live_loop",
  "--sleep-sec", $SleepSec
)
if ([string]::IsNullOrWhiteSpace($Symbol) -eq $false) {
  $args += @("--symbol", $Symbol)
}

$proc = Start-Process `
  -FilePath $pythonPath `
  -ArgumentList $args `
  -WorkingDirectory $Root `
  -PassThru `
  -WindowStyle Hidden `
  -RedirectStandardOutput $absStdoutPath `
  -RedirectStandardError $absStderrPath

Set-Content -Path $absPidPath -Value ([string]$proc.Id) -Encoding ASCII
Start-Sleep -Seconds 2
$alive = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
if (!$alive) {
  Remove-Item -Path $absPidPath -Force -ErrorAction SilentlyContinue
  Write-ControlLog "start_failed process_exited_early stdout=$absStdoutPath stderr=$absStderrPath"
  Write-Error "start_failed process_exited_early stdout=$absStdoutPath stderr=$absStderrPath"
  exit 4
}

Write-ControlLog "started pid=$($proc.Id) sleep_sec=$SleepSec"
Write-Output "started pid=$($proc.Id) sleep_sec=$SleepSec pid_path=$absPidPath stdout=$absStdoutPath stderr=$absStderrPath"
