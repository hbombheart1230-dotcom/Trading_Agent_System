@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\venv\Scripts\python.exe"

if not exist "%PY%" (
  echo python_not_found path=%PY%
  exit /b 3
)

rem Scheduled preopen is a short strategist/portfolio warmup, not the legacy mock-exam gate suite.
"%PY%" "%ROOT%\scripts\run_session.py" ^
  --mode live ^
  --phase preopen ^
  --env-path "%ROOT%\.env" ^
  %*

exit /b %ERRORLEVEL%
