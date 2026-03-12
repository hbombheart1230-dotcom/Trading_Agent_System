@echo off
setlocal

set "ROOT=%~dp0.."
set "SESSION_BAT=%ROOT%\scripts\run_mock_exam_session.bat"
set "MOCK_EXAM_OFFHOURS_PROBE=1"

if not exist "%SESSION_BAT%" (
  echo missing_file %SESSION_BAT%
  exit /b 3
)

call "%SESSION_BAT%" %*
exit /b %ERRORLEVEL%
