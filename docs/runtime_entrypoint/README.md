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
- `live_validation_checklist_2026-04-28.md`
  - preopen live/mock readiness checks
  - first 30-minute validation criteria across runtime, commander, memory, strategist, Kiwoom truth, horizon, and trade report
- `preopen_readiness_2026-04-29.md`
  - mock-live preopen readiness result
  - active loop/watch status before market open
- `strategy_conservatism_review_2026-04-29.md`
  - week-to-date trade and blocker review
  - strategist conservatism diagnosis
  - cost-aware entry, probe-lane, and watchdog improvement plan
- `current_validation_status_2026-04-28.md`
  - current live artifact validation matrix
  - code/document matching map
  - remaining live checks and development checklist

## Current Position

- official trading runtime entrypoint: `scripts/run_session.py`
- intraday live backend: `scripts/run_m13_live_loop.py`
- current live intraday dispatch is Python-to-Python, not shell orchestration
- `.bat` / `.ps1` launchers remain Windows wrappers, not runtime owners
- shared entrypoint helpers now live in:
  - `libs/runtime/entrypoint_common.py`
  - `libs/runtime/live_loop_lock.py`
- runtime output/process query helpers now live in:
  - `libs/runtime/runtime_output_helpers.py`
  - `libs/runtime/live_loop_process_query.py`
- live-loop config helpers now live in:
  - `libs/runtime/live_loop_config.py`
- live-loop orchestration now lives in:
  - `libs/runtime/live_loop_runner.py`
- runtime profile validation supports `mock_live` for Kiwoom mock broker HTTP with auto execution enabled and real-account execution disabled.
- run-session implementation dispatch now lives in:
  - `libs/runtime/session_entry_dispatch.py`
- off-hours validation loop helpers now live in:
  - `libs/runtime/offhours_validation_runtime.py`
- live session summary helpers now live in:
  - `libs/runtime/live_session_summary_helpers.py`
- off-hours validation no longer imports script-private helpers from `run_m13_live_loop.py`
- hot-path runtime scripts now have no direct `scripts.*` imports between them

## Next Work

1. keep `run_session.py` as the single operator-facing entrypoint
2. keep shared lock/path/env/tick helpers out of scripts and add new helpers there first
3. keep `run_m13_live_loop.py` as parse + delegate only
4. keep new runtime helper ownership in `libs/runtime/*` and prevent hot-path script-to-script regressions
5. move lower-priority wrapper/process helpers out of non-hot-path scripts as needed
6. add watchdog behavior for missing lock owners, stale event logs, and canonical-run gaps during market session
