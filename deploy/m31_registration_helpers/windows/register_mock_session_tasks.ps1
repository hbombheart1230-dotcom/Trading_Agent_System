param(
  [string]$TaskPrefix = "TradingAgent-MockSession",
  [string]$Days = "MON,TUE,WED,THU,FRI",
  [string]$StartTime = "09:00",
  [string]$StopTime = "15:31",
  [string]$EnsureIntervalMin = "5",
  [string]$EnsureDuration = "",
  [string]$StartScriptPath = "",
  [string]$StopScriptPath = "",
  [string]$Root = "",
  [string]$SleepSec = "60",
  [string]$PidPath = "data\state\m13_live_loop.pid",
  [string]$LockPath = "data\state\m13_live_loop.lock",
  [string]$LockStaleSec = "1800",
  [ValidateSet("LIMITED", "HIGHEST")]
  [string]$RunLevel = "LIMITED"
)

$ErrorActionPreference = "Stop"

# Resolve project root relative to this script location unless explicitly provided.
if ([string]::IsNullOrWhiteSpace($Root)) {
  $root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
} else {
  $root = (Resolve-Path $Root).Path
}

function Resolve-ScriptLocation {
  param(
    [string]$ConfiguredPath,
    [string]$DefaultPath
  )
  if ([string]::IsNullOrWhiteSpace($ConfiguredPath)) {
    return (Resolve-Path $DefaultPath).Path
  }
  if ([System.IO.Path]::IsPathRooted($ConfiguredPath)) {
    return (Resolve-Path $ConfiguredPath).Path
  }
  return (Resolve-Path (Join-Path $root $ConfiguredPath)).Path
}

$startAbs = Resolve-ScriptLocation -ConfiguredPath $StartScriptPath -DefaultPath (Join-Path $PSScriptRoot "start_mock_session.ps1")
$stopAbs = Resolve-ScriptLocation -ConfiguredPath $StopScriptPath -DefaultPath (Join-Path $PSScriptRoot "stop_mock_session.ps1")

if (!(Test-Path $startAbs)) {
  Write-Error "missing_start_script path=$startAbs"
  exit 3
}
if (!(Test-Path $stopAbs)) {
  Write-Error "missing_stop_script path=$stopAbs"
  exit 3
}

$startTask = "$TaskPrefix-Start"
$ensureTask = "$TaskPrefix-Ensure"
$stopTask = "$TaskPrefix-Stop"

$startParts = @(
  "powershell.exe",
  "-NoProfile",
  "-ExecutionPolicy",
  "Bypass",
  "-File `"$startAbs`""
)
if (-not [string]::IsNullOrWhiteSpace($Root)) {
  $startParts += "-Root `"$root`""
}
if ($SleepSec -ne "60") {
  $startParts += "-SleepSec `"$SleepSec`""
}
if ($PidPath -ne "data\state\m13_live_loop.pid") {
  $startParts += "-PidPath `"$PidPath`""
}
if ($LockPath -ne "data\state\m13_live_loop.lock") {
  $startParts += "-LockPath `"$LockPath`""
}
if ($LockStaleSec -ne "1800") {
  $startParts += "-LockStaleSec `"$LockStaleSec`""
}

$stopParts = @(
  "powershell.exe",
  "-NoProfile",
  "-ExecutionPolicy",
  "Bypass",
  "-File `"$stopAbs`""
)
if (-not [string]::IsNullOrWhiteSpace($Root)) {
  $stopParts += "-Root `"$root`""
}
if ($PidPath -ne "data\state\m13_live_loop.pid") {
  $stopParts += "-PidPath `"$PidPath`""
}

$startTr = $startParts -join " "
$stopTr = $stopParts -join " "

schtasks /Create /TN $startTask /SC WEEKLY /D $Days /ST $StartTime /TR $startTr /RL $RunLevel /F | Out-Null
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

function Parse-TimeToMinutes {
  param([string]$TimeText)
  if ([string]::IsNullOrWhiteSpace($TimeText)) { return -1 }
  $parts = $TimeText.Split(":")
  if ($parts.Count -lt 2) { return -1 }
  $h = 0
  $m = 0
  if (-not [int]::TryParse($parts[0], [ref]$h)) { return -1 }
  if (-not [int]::TryParse($parts[1], [ref]$m)) { return -1 }
  if ($h -lt 0 -or $h -gt 23 -or $m -lt 0 -or $m -gt 59) { return -1 }
  return ($h * 60 + $m)
}

function Minutes-ToDuration {
  param([int]$Minutes)
  $mins = [Math]::Max(1, $Minutes)
  $h = [int][Math]::Floor($mins / 60)
  $m = [int]($mins % 60)
  return ("{0:D2}:{1:D2}" -f $h, $m)
}

$ensureEvery = 0
[void][int]::TryParse($EnsureIntervalMin, [ref]$ensureEvery)
if ($ensureEvery -gt 0) {
  $ensureDu = $EnsureDuration
  if ([string]::IsNullOrWhiteSpace($ensureDu)) {
    $startMin = Parse-TimeToMinutes -TimeText $StartTime
    $stopMin = Parse-TimeToMinutes -TimeText $StopTime
    if ($startMin -ge 0 -and $stopMin -gt $startMin) {
      $ensureDu = Minutes-ToDuration -Minutes ($stopMin - $startMin)
    } else {
      $ensureDu = "06:31"
    }
  }

  schtasks /Create /TN $ensureTask /SC WEEKLY /D $Days /ST $StartTime /RI $EnsureIntervalMin /DU $ensureDu /TR $startTr /RL $RunLevel /F | Out-Null
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}

schtasks /Create /TN $stopTask /SC WEEKLY /D $Days /ST $StopTime /TR $stopTr /RL $RunLevel /F | Out-Null
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Output "ok start_task=$startTask ensure_task=$ensureTask ensure_interval_min=$EnsureIntervalMin stop_task=$stopTask days=$Days start=$StartTime stop=$StopTime root=$root run_level=$RunLevel"
