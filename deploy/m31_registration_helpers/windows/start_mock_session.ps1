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

function Read-LockOwnerPid {
  param([string]$Path)
  if (!(Test-Path $Path)) {
    return 0
  }
  try {
    $obj = Get-Content $Path -Raw | ConvertFrom-Json
    $owner = [int]($obj.pid)
    if ($owner -gt 0 -and (Get-Process -Id $owner -ErrorAction SilentlyContinue)) {
      return $owner
    }
  } catch {}
  return 0
}

function Get-LoopRows {
  param(
    [string]$ResolvedRoot,
    [string]$AbsLockPath
  )
  return @(
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
      $cmd = [string]$_.CommandLine
      (
        ($cmd -like "*scripts/run_m13_live_loop.py*") -or
        ($cmd -like "*-m scripts.run_m13_live_loop*")
      ) -and (
        ($cmd -like "*$AbsLockPath*") -or
        ($cmd -like "*$ResolvedRoot*")
      )
    } | Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine
  )
}

function Resolve-RuntimePid {
  param(
    [array]$Rows,
    [int]$LockOwnerPid
  )
  if (!$Rows -or $Rows.Count -le 0) {
    return 0
  }
  $byPid = @{}
  $parentSet = @{}
  foreach ($r in $Rows) {
    $pidVal = [int]$r.ProcessId
    if ($pidVal -le 0) { continue }
    $byPid[$pidVal] = $r
    $pp = [int]$r.ParentProcessId
    if ($pp -gt 0) { $parentSet[$pp] = $true }
  }
  if ($LockOwnerPid -gt 0 -and $byPid.ContainsKey($LockOwnerPid)) {
    return $LockOwnerPid
  }
  $leafRows = @($Rows | Where-Object { -not $parentSet.ContainsKey([int]$_.ProcessId) })
  $selected = $null
  if ($leafRows.Count -gt 0) {
    $selected = $leafRows | Sort-Object ProcessId -Descending | Select-Object -First 1
  } else {
    $selected = $Rows | Sort-Object ProcessId -Descending | Select-Object -First 1
  }
  if ($selected) {
    return [int]$selected.ProcessId
  }
  return 0
}

function Resolve-RuntimeChainPids {
  param(
    [array]$Rows,
    [int]$RuntimePid
  )
  if (!$Rows -or $Rows.Count -le 0 -or $RuntimePid -le 0) {
    return @()
  }
  $byPid = @{}
  foreach ($r in $Rows) {
    $pidVal = [int]$r.ProcessId
    if ($pidVal -gt 0) { $byPid[$pidVal] = $r }
  }
  if (-not $byPid.ContainsKey($RuntimePid)) {
    return @()
  }
  $related = @{}
  $related[$RuntimePid] = $true
  $cur = $byPid[$RuntimePid]
  while ($cur) {
    $pp = [int]$cur.ParentProcessId
    if ($pp -le 0 -or -not $byPid.ContainsKey($pp)) { break }
    $related[$pp] = $true
    $cur = $byPid[$pp]
  }
  $changed = $true
  while ($changed) {
    $changed = $false
    foreach ($r in $Rows) {
      $pidVal = [int]$r.ProcessId
      $pp = [int]$r.ParentProcessId
      if ($pidVal -le 0) { continue }
      if ($related.ContainsKey($pidVal)) { continue }
      if ($pp -gt 0 -and $related.ContainsKey($pp)) {
        $related[$pidVal] = $true
        $changed = $true
      }
    }
  }
  $pids = @($related.Keys | ForEach-Object { [int]$_ } | Sort-Object)
  return $pids
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

$existingRows = Get-LoopRows -ResolvedRoot $resolvedRoot -AbsLockPath $absLockPath
if ($existingRows.Count -gt 0) {
  $lockOwnerPid = Read-LockOwnerPid -Path $absLockPath
  $runtimePid = Resolve-RuntimePid -Rows $existingRows -LockOwnerPid $lockOwnerPid
  $runtimeChainPids = Resolve-RuntimeChainPids -Rows $existingRows -RuntimePid $runtimePid
  if ($runtimePid -le 0) {
    $runtimePid = [int]$existingRows[0].ProcessId
  }
  Set-Content -Path $absPidPath -Value ([string]$runtimePid) -Encoding ASCII
  Write-ControlLog "already_running runtime_pid=$runtimePid lock_owner_pid=$lockOwnerPid raw_process_count=$($existingRows.Count) runtime_chain_pids=$([string]::Join(',', $runtimeChainPids))"
  Write-Output "already_running runtime_pid=$runtimePid lock_owner_pid=$lockOwnerPid raw_process_count=$($existingRows.Count) logical_instance_count=1"
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

$lockOwnerPid = Read-LockOwnerPid -Path $absLockPath
$rowsAfterStart = Get-LoopRows -ResolvedRoot $resolvedRoot -AbsLockPath $absLockPath
$runtimePid = Resolve-RuntimePid -Rows $rowsAfterStart -LockOwnerPid $lockOwnerPid
if ($runtimePid -le 0) {
  $runtimePid = [int]$proc.Id
}
Set-Content -Path $absPidPath -Value ([string]$runtimePid) -Encoding ASCII
$runtimeChainPids = Resolve-RuntimeChainPids -Rows $rowsAfterStart -RuntimePid $runtimePid

Write-ControlLog "started launcher_pid=$($proc.Id) runtime_pid=$runtimePid lock_owner_pid=$lockOwnerPid raw_process_count=$($rowsAfterStart.Count) runtime_chain_pids=$([string]::Join(',', $runtimeChainPids)) root=$resolvedRoot sleep_sec=$SleepSec lock=$absLockPath"
Write-Output "started launcher_pid=$($proc.Id) runtime_pid=$runtimePid lock_owner_pid=$lockOwnerPid raw_process_count=$($rowsAfterStart.Count) logical_instance_count=1 root=$resolvedRoot sleep_sec=$SleepSec lock=$absLockPath pid_path=$absPidPath stdout=$absStdoutPath stderr=$absStderrPath"
