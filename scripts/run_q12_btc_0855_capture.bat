@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\venv\Scripts\python.exe"

if not exist "%PY%" (
  echo python_not_found path=%PY%
  exit /b 3
)

pushd "%ROOT%"
"%PY%" "%ROOT%\scripts\capture_q12_btc_0855_snapshot.py" ^
  --env-path "%ROOT%\.env" ^
  --root "%ROOT%\data\logs\q12_btc_0855"
set "RUN_RC=%ERRORLEVEL%"
popd
exit /b %RUN_RC%
