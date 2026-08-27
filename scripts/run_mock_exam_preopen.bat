@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\venv\Scripts\python.exe"

if not exist "%PY%" (
  echo python_not_found path=%PY%
  exit /b 3
)

pushd "%ROOT%"

rem Capture point-in-time macro/index evidence before the first opening decision.
"%PY%" "%ROOT%\scripts\capture_preopen_macro_snapshot.py" ^
  --env-path "%ROOT%\.env" ^
  --state-path "%ROOT%\data\state.json"
set "CAPTURE_RC=%ERRORLEVEL%"

rem Scheduled preopen is a short strategist/portfolio warmup, not the legacy mock-exam gate suite.
"%PY%" "%ROOT%\scripts\run_session.py" ^
  --mode live ^
  --phase preopen ^
  --env-path "%ROOT%\.env" ^
  %*

set "RUN_RC=%ERRORLEVEL%"

rem Additive observability only. Its failure never changes the existing preopen result.
"%PY%" "%ROOT%\scripts\run_scheduled_intelligence.py" ^
  --phase preopen ^
  --capture-rc %CAPTURE_RC% ^
  --session-rc %RUN_RC% ^
  --reports-root "%ROOT%\reports"
popd
exit /b %RUN_RC%
