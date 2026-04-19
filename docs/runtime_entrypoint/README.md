# Runtime Entrypoint

## Scope

This folder tracks the trading runtime entry boundary around:

- `scripts/run_session.py`
- `scripts/run_m13_live_loop.py`

The goal is to keep scripts as process boundaries only and move reusable
runtime ownership into libs/graphs modules.

## Current Documents

- `m13_live_boundary_audit_2026-04-19.md`
  - current call chain
  - current boundary violations
  - next extraction plan
- `process_launch_modes_2026-04-19.md`
  - how the runtime is actually started today
  - which wrappers are compatibility helpers

## Current Position

- official trading runtime entrypoint: `scripts/run_session.py`
- intraday live backend: `scripts/run_m13_live_loop.py`
- current live intraday dispatch is Python-to-Python, not shell orchestration
- `.bat` / `.ps1` launchers remain Windows wrappers, not runtime owners

## Next Work

1. keep `run_session.py` as the single operator-facing entrypoint
2. extract shared lock/path/env/session helpers out of `run_m13_live_loop.py`
3. reduce `run_m13_live_loop.py` to a thin wrapper around module-owned loop logic
4. update downstream scripts that currently import helper functions from `run_m13_live_loop.py`
