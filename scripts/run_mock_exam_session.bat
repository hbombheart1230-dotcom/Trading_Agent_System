@echo off
setlocal

set "ROOT=%~dp0.."
set "RESTART_BAT=%ROOT%\scripts\restart_live_session.bat"

if not exist "%RESTART_BAT%" (
  echo restart_wrapper_not_found path=%RESTART_BAT%
  exit /b 3
)

rem Scheduled regular-session startup must never inherit off-hours operation.
call "%RESTART_BAT%" --log-tag scheduled_start --no-allow-offhours --session-hard-gate %*
exit /b %ERRORLEVEL%
