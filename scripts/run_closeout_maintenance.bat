@echo off
setlocal
cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8
set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
if not exist "reports\runtime" mkdir "reports\runtime"
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "D=%%a%%b%%c"
for /f "tokens=1-3 delims=:." %%a in ("%time%") do set "T=%%a%%b%%c"
set "T=%T: =0%"
set "LOG=reports\runtime\closeout_maintenance_%D%_%T%.log"
echo closeout_start %date% %time% args=%* > "%LOG%"
"%PY%" scripts\run_closeout_maintenance.py %* >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo closeout_exit %date% %time% rc=%RC% >> "%LOG%"
type "%LOG%"
exit /b %RC%
