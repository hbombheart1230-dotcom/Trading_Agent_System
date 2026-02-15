# M21-4: Runtime Transition Controls (cancel/pause/retry)

- Date: 2026-02-15
- Goal: formalize operator/runtime transitions in commander entry without changing default execution path.

## Scope (minimal)

1. Add transition control handling in canonical commander runtime.
2. Keep behavior unchanged when no transition control is provided.
3. Add unit tests for cancel/pause/retry semantics.

## Implemented

- File: `graphs/commander_runtime.py`
  - Added runtime control handling via `state["runtime_control"]`:
    - `cancel`: short-circuit run with `runtime_status="cancelled"`
    - `pause`: short-circuit run with `runtime_status="paused"`
    - `retry`: set `runtime_status="retrying"`, increment `runtime_retry_count`, then continue normal mode run
  - Added state markers:
    - `runtime_transition`
    - `runtime_status`
    - `runtime_retry_count` (retry only)

- File: `tests/test_m21_commander_runtime_entry.py`
  - Added tests for:
    - cancel short-circuit (no node run)
    - pause short-circuit (no node run)
    - retry continues run and increments retry counter

## Safety Notes

- No transition key (`runtime_control`) means existing behavior is preserved.
- Default runtime mode remains `graph_spine`.
