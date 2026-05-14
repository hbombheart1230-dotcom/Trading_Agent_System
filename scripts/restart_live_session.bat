@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\venv\Scripts\python.exe"

if not exist "%PY%" (
  set "PY=python"
)

"%PY%" "%ROOT%\scripts\restart_live_session.py" %*
exit /b %ERRORLEVEL%
