@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\venv\Scripts\python.exe"

if not exist "%PY%" (
  set "PY=python"
)

rem Compatibility wrapper. Official trading runtime entrypoint is scripts/run_session.py
"%PY%" "%ROOT%\scripts\run_session.py" ^
  --mode live ^
  --phase watch ^
  --env-path "%ROOT%\.env" ^
  --event-log-path "%ROOT%\data\logs\events.jsonl" ^
  --summary-report-dir "%ROOT%\reports\live_summary" ^
  --watch-report-dir "%ROOT%\reports\live_watch" ^
  --sleep-sec 300 ^
  %*

exit /b %ERRORLEVEL%
