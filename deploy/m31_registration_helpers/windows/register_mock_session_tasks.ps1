param(
  [string]$TaskPrefix = "TradingAgent-MockSession",
  [string]$Days = "MON,TUE,WED,THU,FRI",
  [string]$StartTime = "09:00",
  [string]$StopTime = "15:31",
  [string]$StartScriptPath = "deploy\m31_registration_helpers\windows\start_mock_session.ps1",
  [string]$StopScriptPath = "deploy\m31_registration_helpers\windows\stop_mock_session.ps1"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path ".").Path
$startAbs = Join-Path $root $StartScriptPath
$stopAbs = Join-Path $root $StopScriptPath

if (!(Test-Path $startAbs)) {
  Write-Error "missing_start_script path=$startAbs"
  exit 3
}
if (!(Test-Path $stopAbs)) {
  Write-Error "missing_stop_script path=$stopAbs"
  exit 3
}

$startTask = "$TaskPrefix-Start"
$stopTask = "$TaskPrefix-Stop"
$startTr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$startAbs`""
$stopTr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$stopAbs`""

schtasks /Create /TN $startTask /SC WEEKLY /D $Days /ST $StartTime /TR $startTr /F | Out-Null
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

schtasks /Create /TN $stopTask /SC WEEKLY /D $Days /ST $StopTime /TR $stopTr /F | Out-Null
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Output "ok start_task=$startTask stop_task=$stopTask days=$Days start=$StartTime stop=$StopTime"
