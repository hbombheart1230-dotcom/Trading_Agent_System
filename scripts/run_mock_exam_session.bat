@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\venv\Scripts\python.exe"
set "SESSION_EXTRA="

rem Optional off-hours probe mode (env-driven):
rem   set MOCK_EXAM_OFFHOURS_PROBE=1
if /I "%MOCK_EXAM_OFFHOURS_PROBE%"=="1" (
  set "SESSION_EXTRA=%SESSION_EXTRA% --allow-offhours-session-probe"
)
if not "%MOCK_EXAM_PROBE_SYMBOL%"=="" (
  set "SESSION_EXTRA=%SESSION_EXTRA% --probe-symbol %MOCK_EXAM_PROBE_SYMBOL%"
)
if not "%MOCK_EXAM_PROBE_PRICE%"=="" (
  set "SESSION_EXTRA=%SESSION_EXTRA% --probe-price %MOCK_EXAM_PROBE_PRICE%"
)
if not "%MOCK_EXAM_PROBE_CASH%"=="" (
  set "SESSION_EXTRA=%SESSION_EXTRA% --probe-cash %MOCK_EXAM_PROBE_CASH%"
)

if not exist "%PY%" (
  echo python_not_found path=%PY%
  exit /b 3
)

"%PY%" -m scripts.run_mock_exam_day ^
  --phase session ^
  --env-path "%ROOT%\.env" ^
  --report-dir "%ROOT%\reports\mock_exam_day" ^
  --event-log-path "%ROOT%\data\logs\events.jsonl" ^
  --sleep-sec 60 ^
  %SESSION_EXTRA% ^
  %*

exit /b %ERRORLEVEL%
