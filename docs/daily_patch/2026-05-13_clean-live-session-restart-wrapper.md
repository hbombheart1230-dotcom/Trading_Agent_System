# 2026-05-13 Clean Live Session Restart Wrapper

## Background

- Live restart had been handled manually by checking Python processes, lock ownership, stale lock state, log files, and heartbeat status.
- On Windows, the venv Python launcher can show a parent/child pair for the same command. Report generation workers may also appear as child processes while a trade report is being built.
- Operators should not need to reason about those details during market hours.

## Change

- Added `scripts/restart_live_session.py`.
  - Stops existing live intraday loop processes.
  - Removes the old loop lock after the previous loop is stopped.
  - Starts one new `scripts/run_session.py --mode live --phase intraday` session.
  - Waits for lock owner and heartbeat/process visibility.
  - Prints a concise status with lock PID, heartbeat, session PIDs, stdout path, and stderr size.

- Added wrappers:
  - `scripts/restart_live_session.ps1`
  - `scripts/restart_live_session.bat`

- Fixed Windows process discovery in `libs/runtime/live_loop_process_query.py`.
  - The previous query matched `scripts/run_session.py` but missed Windows command lines containing `scripts\run_session.py`.
  - This caused status checks to show an alive lock PID but empty `session_pids`.

## Operator Command

```powershell
.\scripts\restart_live_session.bat
```

Status only:

```powershell
.\scripts\restart_live_session.bat --status-only
```

JSON output:

```powershell
.\scripts\restart_live_session.bat --json
```

## Notes

- The actual runtime still uses the official entrypoint `scripts/run_session.py`.
- The parent/child process shape is not an operational problem; the wrapper treats it as one live session and reports the lock owner as the canonical PID.
- `scripts/restart_live_session.ps1` is also available, but some Windows machines block direct `.ps1` execution by policy. The `.bat` wrapper works from PowerShell without changing execution policy.

## Verification

- `.\scripts\restart_live_session.bat --status-only`
  - confirmed running session and lock PID.
- `.\scripts\restart_live_session.bat`
  - clean restart succeeded.
  - lock PID: `15528`
  - session PIDs: `[30168, 15528]`
  - stderr: `0 bytes`
- Syntax checked without pycache writes:
  - `scripts/restart_live_session.py`
  - `libs/runtime/live_loop_process_query.py`
