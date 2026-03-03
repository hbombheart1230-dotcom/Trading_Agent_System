param(
  [string]$TaskPrefix = "TradingAgent-MockSession"
)

$ErrorActionPreference = "Stop"

$startTask = "$TaskPrefix-Start"
$stopTask = "$TaskPrefix-Stop"

schtasks /Delete /TN $startTask /F | Out-Null
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
  exit $LASTEXITCODE
}

schtasks /Delete /TN $stopTask /F | Out-Null
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
  exit $LASTEXITCODE
}

Write-Output "ok deleted_tasks=$startTask,$stopTask"
