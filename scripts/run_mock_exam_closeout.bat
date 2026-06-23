@echo off
setlocal

set "ROOT=%~dp0.."
set "CLOSEOUT_BAT=%ROOT%\scripts\run_closeout_maintenance.bat"

if not exist "%CLOSEOUT_BAT%" (
  echo closeout_wrapper_not_found path=%CLOSEOUT_BAT%
  exit /b 3
)

rem Time-based fallback. Kiwoom market-status events are the primary closeout trigger.
call "%CLOSEOUT_BAT%" --trigger scheduled_closeout_fallback %*
exit /b %ERRORLEVEL%
