@echo off
setlocal

set "ROOT=%~dp0.."
set "EVENT_LOG_PATH=%ROOT%\data\logs\events.jsonl"
set "SUMMARY_REPORT_DIR=%ROOT%\reports\live_summary"
set "WATCH_REPORT_DIR=%ROOT%\reports\live_watch"

python "%ROOT%\scripts\run_live_session_watch.py" ^
  --event-log-path "%EVENT_LOG_PATH%" ^
  --summary-report-dir "%SUMMARY_REPORT_DIR%" ^
  --watch-report-dir "%WATCH_REPORT_DIR%" ^
  --sleep-sec 300 ^
  %*

exit /b %ERRORLEVEL%
