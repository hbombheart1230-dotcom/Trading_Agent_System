param(
  [string]$Root = "",
  [string]$PidPath = "data\state\m13_live_loop.pid",
  [string]$LockPath = "data\state\m13_live_loop.lock",
  [string]$ControlLogPath = "data\logs\m31_mock_session_control.log"
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Root)) {
  $resolvedRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
} else {
  $resolvedRoot = (Resolve-Path $Root).Path
}
$absPidPath = Join-Path $resolvedRoot $PidPath
$absLockPath = Join-Path $resolvedRoot $LockPath
$absControlLogPath = Join-Path $resolvedRoot $ControlLogPath
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
  $exists = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
  if (!$exists) {
    return $false
  }
  try {
    $null = & taskkill /PID $PidValue /T /F
  } catch {
    Stop-Process -Id $PidValue -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Milliseconds 200
  $remaining = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
  return ($null -eq $remaining)
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
    } | Select-Object ProcessId, ParentProcessId
  )
}

function Resolve-RootRuntimePids {
  param([array]$Rows)
  if (!$Rows -or $Rows.Count -le 0) {
    return @()
  }
  $byPid = @{}
  foreach ($r in $Rows) {
    $pidVal = [int]$r.ProcessId
    if ($pidVal -gt 0) {
      $byPid[$pidVal] = $r
    }
  }
  $roots = @()
  foreach ($pidKey in $byPid.Keys) {
    $row = $byPid[$pidKey]
    $pp = [int]$row.ParentProcessId
    if ($pp -le 0 -or -not $byPid.ContainsKey($pp)) {
      $roots += [int]$pidKey
    }
  }
  return @($roots | Sort-Object)
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

$lockOwnerPid = Read-LockOwnerPid -Path $absLockPath
if ($lockOwnerPid -gt 0) {
  if (Stop-ById -PidValue $lockOwnerPid) {
    $stopped += 1
  }
}

$fallbackRows = Get-LoopRows -ResolvedRoot $resolvedRoot -AbsLockPath $absLockPath
$rootPids = @(Resolve-RootRuntimePids -Rows $fallbackRows)
foreach ($pidVal in $rootPids) {
  if (Stop-ById -PidValue $pidVal) {
    $stopped += 1
  }
}

$rootPidText = ""
if ($rootPids -and $rootPids.Count -gt 0) {
  $rootPidText = [string]::Join(',', $rootPids)
}

Remove-Item -Path $absLockPath -Force -ErrorAction SilentlyContinue

Write-ControlLog "stopped_total=$stopped lock_owner_pid=$lockOwnerPid root_runtime_pids=$rootPidText pid_path=$absPidPath lock_path=$absLockPath"
Write-Output "stopped_total=$stopped lock_owner_pid=$lockOwnerPid root_runtime_pids=$rootPidText pid_path=$absPidPath lock_path=$absLockPath"
