@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\venv\Scripts\python.exe"

if not exist "%PY%" (
  echo python_not_found path=%PY%
  exit /b 3
)

rem Scheduled regular-session startup owns the whole day stack:
rem live session + Q10/Q11/Q12 shadow baselines with today's date.
"%PY%" "%ROOT%\scripts\start_trading_day.py" --mode start %*
exit /b %ERRORLEVEL%
