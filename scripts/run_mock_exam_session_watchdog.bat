@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\venv\Scripts\python.exe"

if not exist "%PY%" (
  echo python_not_found path=%PY%
  exit /b 3
)

"%PY%" "%ROOT%\scripts\start_trading_day.py" --mode watchdog --lookback-min 10 %*
exit /b %ERRORLEVEL%
