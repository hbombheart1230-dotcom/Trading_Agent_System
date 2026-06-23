@echo off
setlocal

set "ROOT=%~dp0.."
set "RESTART_BAT=%ROOT%\scripts\restart_live_session.bat"

if not exist "%RESTART_BAT%" (
  echo restart_wrapper_not_found path=%RESTART_BAT%
  exit /b 3
)

rem Scheduled session startup must use the same clean restart path as manual operation.
call "%RESTART_BAT%" --log-tag scheduled_start %*
exit /b %ERRORLEVEL%
