@echo off
setlocal

set "ROOT=%~dp0.."
set "SESSION_BAT=%ROOT%\scripts\run_mock_exam_session.bat"
set "RESTART_BAT=%ROOT%\scripts\restart_live_session.bat"

if not exist "%SESSION_BAT%" (
  echo missing_file %SESSION_BAT%
  exit /b 3
)
if not exist "%RESTART_BAT%" (
  echo missing_file %RESTART_BAT%
  exit /b 3
)

set "LIVE_STATUS="
for /f "tokens=2 delims==" %%i in ('call "%RESTART_BAT%" --status-only ^| findstr /b "live_status="') do set "LIVE_STATUS=%%i"

if /I "%LIVE_STATUS%"=="running" (
  echo ok session_loop_alive
  exit /b 0
)

echo watchdog_restart session_loop_missing
call "%SESSION_BAT%" %*
exit /b %ERRORLEVEL%
