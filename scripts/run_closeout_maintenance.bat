@echo off
setlocal
cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8
set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" scripts\run_closeout_maintenance.py %*
exit /b %ERRORLEVEL%
