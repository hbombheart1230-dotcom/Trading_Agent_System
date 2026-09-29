param(
  [string]$TaskName = "TradingAgent-DailyUefEvaluation",
  [string]$TaskXmlPath = "deploy\m28_launch_templates\windows\daily_uef_evaluation_task.xml"
)

# Not invoked automatically by any P1.2 task -- registering a Windows
# Scheduled Task changes this host's live automation and is deliberately
# left as a manual, explicit step, mirroring the caution already applied
# to the existing commander-runtime scheduler task registration.

if (!(Test-Path $TaskXmlPath)) {
  Write-Error "missing_task_xml path=$TaskXmlPath"
  exit 3
}

schtasks /Create /TN $TaskName /XML $TaskXmlPath /F
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Output "ok role=daily_uef_evaluation task=$TaskName"
