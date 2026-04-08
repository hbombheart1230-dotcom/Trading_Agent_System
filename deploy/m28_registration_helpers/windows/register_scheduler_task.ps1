param(
  [string]$TaskName = "TradingAgent-Scheduler-dev",
  [string]$TaskXmlPath = "deploy\m28_launch_templates\windows\scheduler_task.xml"
)

if (!(Test-Path $TaskXmlPath)) {
  Write-Error "missing_task_xml path=$TaskXmlPath"
  exit 3
}

schtasks /Create /TN $TaskName /XML $TaskXmlPath /F
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Output "ok role=scheduler profile=dev task=$TaskName"
