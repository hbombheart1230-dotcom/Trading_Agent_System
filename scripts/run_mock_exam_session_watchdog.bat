@echo off
setlocal

set "ROOT=%~dp0.."
set "SESSION_BAT=%ROOT%\scripts\run_mock_exam_session.bat"

if not exist "%SESSION_BAT%" (
  echo missing_file %SESSION_BAT%
  exit /b 3
)

set "HAS_LOOP=0"
for /f %%i in ('powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process ^| Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*scripts.run_m13_live_loop*' }; if ($p) { '1' } else { '0' }"') do set "HAS_LOOP=%%i"

if "%HAS_LOOP%"=="1" (
  echo ok session_loop_alive
  exit /b 0
)

echo watchdog_restart session_loop_missing
call "%SESSION_BAT%" %*
exit /b %ERRORLEVEL%

