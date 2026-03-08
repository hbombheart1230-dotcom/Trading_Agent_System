@echo off
setlocal

set "ROOT=%~dp0.."
set "PY=%ROOT%\venv\Scripts\python.exe"

if not exist "%PY%" (
  echo python_not_found path=%PY%
  exit /b 3
)

"%PY%" -m scripts.run_mock_exam_day ^
  --phase preopen ^
  --env-path "%ROOT%\.env" ^
  --report-dir "%ROOT%\reports\mock_exam_day" ^
  --event-log-path "%ROOT%\data\logs\events.jsonl" ^
  %*

exit /b %ERRORLEVEL%
