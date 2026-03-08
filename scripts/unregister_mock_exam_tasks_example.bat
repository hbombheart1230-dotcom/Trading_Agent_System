@echo off
setlocal

set "TASK_PREFIX=TradingAgent-MockExamDay"

schtasks /Delete /TN "%TASK_PREFIX%-Preopen" /F >nul 2>&1
schtasks /Delete /TN "%TASK_PREFIX%-Session" /F >nul 2>&1
schtasks /Delete /TN "%TASK_PREFIX%-Closeout" /F >nul 2>&1

echo ok deleted_tasks=%TASK_PREFIX%-Preopen,%TASK_PREFIX%-Session,%TASK_PREFIX%-Closeout
exit /b 0
