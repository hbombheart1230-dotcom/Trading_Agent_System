# Process Launch Modes

## Short Answer

The trading runtime is currently started mainly by direct Python entrypoints.

It is not primarily driven by `sh`.

On Windows, `.bat` and `.ps1` files exist as compatibility wrappers and task
helpers, not as the real runtime owners.

## Current Official Runtime Commands

Examples:

- `python scripts/run_session.py --mode live --phase intraday`
- `python scripts/run_session.py --mode live --phase preopen`
- `python scripts/run_session.py --mode mock --phase intraday`

In local Windows usage this is often:

- `venv\\Scripts\\python.exe scripts\\run_session.py ...`

## Current Launch Ownership

### Primary owner

- `scripts/run_session.py`

This is the official trading runtime entrypoint.

### Intraday live backend

- `scripts/run_m13_live_loop.py`

This is currently dispatched in-process from `run_session.py`.

That means the normal live intraday path is:

- Python process starts `run_session.py`
- `run_session.py` imports and calls `run_m13_live_loop.main(...)`

This is not shell-to-shell orchestration.

## Wrapper Types Still Present

### Batch wrappers

Example:

- `scripts/run_mock_exam_session.bat`

These are convenience or compatibility wrappers. They delegate to
`scripts/run_session.py`.

### PowerShell wrappers

Examples:

- `deploy/m31_registration_helpers/windows/start_mock_session.ps1`
- `deploy/m31_registration_helpers/windows/stop_mock_session.ps1`

These exist for Windows task control, deployment, and operator convenience.

## Practical Interpretation

If we say "how does the process run today?" the accurate answer is:

1. official owner: direct Python
2. compatibility wrappers: `.bat`
3. Windows ops/task wrappers: `.ps1`
4. not `sh`

## Cleanup Implication

Because the real owner is already Python:

- we should clean `run_session.py` and `run_m13_live_loop.py`
- we should not spend time treating `.bat` / `.ps1` as core runtime owners
- wrappers should stay thin and dumb
