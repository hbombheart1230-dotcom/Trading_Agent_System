@echo off
setlocal

set "ROOT=%~dp0.."
set "PREOPEN_BAT=%ROOT%\scripts\run_mock_exam_preopen.bat"
set "SESSION_BAT=%ROOT%\scripts\run_mock_exam_session.bat"
set "SESSION_WATCHDOG_BAT=%ROOT%\scripts\run_mock_exam_session_watchdog.bat"
set "CLOSEOUT_BAT=%ROOT%\scripts\run_mock_exam_closeout.bat"

if not exist "%PREOPEN_BAT%" (
  echo missing_file %PREOPEN_BAT%
  exit /b 3
)
if not exist "%SESSION_BAT%" (
  echo missing_file %SESSION_BAT%
  exit /b 3
)
if not exist "%SESSION_WATCHDOG_BAT%" (
  echo missing_file %SESSION_WATCHDOG_BAT%
  exit /b 3
)
if not exist "%CLOSEOUT_BAT%" (
  echo missing_file %CLOSEOUT_BAT%
  exit /b 3
)

set "TASK_PREFIX=TradingAgent-MockExamDay"
set "DAYS=MON,TUE,WED,THU,FRI"

schtasks /Create /TN "%TASK_PREFIX%-Preopen" /SC WEEKLY /D %DAYS% /ST 08:50 /TR "\"%PREOPEN_BAT%\"" /RL LIMITED /F
if errorlevel 1 exit /b %errorlevel%

schtasks /Create /TN "%TASK_PREFIX%-Session" /SC WEEKLY /D %DAYS% /ST 09:00 /TR "\"%SESSION_BAT%\"" /RL LIMITED /F
if errorlevel 1 exit /b %errorlevel%

schtasks /Create /TN "%TASK_PREFIX%-SessionWatchdog" /SC WEEKLY /D %DAYS% /ST 09:05 /RI 5 /DU 06:20 /TR "\"%SESSION_WATCHDOG_BAT%\"" /RL LIMITED /F
if errorlevel 1 exit /b %errorlevel%

schtasks /Create /TN "%TASK_PREFIX%-Closeout" /SC WEEKLY /D %DAYS% /ST 16:00 /TR "\"%CLOSEOUT_BAT%\"" /RL LIMITED /F
if errorlevel 1 exit /b %errorlevel%

echo ok registered_tasks=%TASK_PREFIX%-Preopen,%TASK_PREFIX%-Session,%TASK_PREFIX%-SessionWatchdog,%TASK_PREFIX%-Closeout
exit /b 0
