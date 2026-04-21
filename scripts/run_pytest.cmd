@echo off
setlocal
set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..
"%REPO_ROOT%\venv\Scripts\python.exe" "%SCRIPT_DIR%run_pytest.py" %*
exit /b %ERRORLEVEL%
