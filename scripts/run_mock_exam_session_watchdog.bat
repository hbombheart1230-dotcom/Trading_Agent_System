@echo off
setlocal

set "ROOT=%~dp0.."
set "SESSION_BAT=%ROOT%\scripts\run_mock_exam_session.bat"
set "LOCK_PATH=%ROOT%\data\state\m13_live_loop.lock"

if not exist "%SESSION_BAT%" (
  echo missing_file %SESSION_BAT%
  exit /b 3
)

set "HAS_LOOP=0"
for /f %%i in ('powershell -NoProfile -Command "$root = [System.IO.Path]::GetFullPath('%ROOT%'); $lock = [System.IO.Path]::GetFullPath('%LOCK_PATH%'); $has = $false; if (Test-Path $lock) { try { $obj = Get-Content $lock -Raw ^| ConvertFrom-Json; $pid = [int]($obj.pid); if ($pid -gt 0 -and (Get-Process -Id $pid -ErrorAction SilentlyContinue)) { $has = $true } } catch {} }; if (-not $has) { $p = Get-CimInstance Win32_Process ^| Where-Object { $cmd = [string]$_.CommandLine; $_.Name -eq 'python.exe' -and ((((($cmd -like '*scripts/run_session.py*') -or ($cmd -like '*-m scripts.run_session*')) -and ($cmd -like '*--phase intraday*')) -or ($cmd -like '*scripts/run_m13_live_loop.py*') -or ($cmd -like '*-m scripts.run_m13_live_loop*')) -and (($cmd -like ('*' + $lock + '*')) -or ($cmd -like ('*' + $root + '*')))) }; if ($p) { $has = $true } }; if ($has) { '1' } else { '0' }"') do set "HAS_LOOP=%%i"

if "%HAS_LOOP%"=="1" (
  echo ok session_loop_alive
  exit /b 0
)

echo watchdog_restart session_loop_missing
call "%SESSION_BAT%" %*
exit /b %ERRORLEVEL%
