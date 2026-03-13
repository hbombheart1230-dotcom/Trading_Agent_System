@echo off
setlocal

set "MOCK_EXAM_OFFHOURS_SIMULATED=1"
call "%~dp0run_mock_exam_session.bat" %*
exit /b %ERRORLEVEL%
