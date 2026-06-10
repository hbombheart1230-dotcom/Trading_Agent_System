@echo off
setlocal
cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8
python scripts\run_closeout_maintenance.py %*
exit /b %ERRORLEVEL%
