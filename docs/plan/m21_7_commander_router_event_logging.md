# M21-7: Commander Router Event Logging

- Date: 2026-02-15
- Goal: make canonical runtime routing observable with explicit commander-level events.

## Scope (minimal)

1. Emit commander runtime route/transition/end events.
2. Support injected logger for tests and local tooling.
3. Keep runtime behavior unchanged.

## Implemented

- File: `graphs/commander_runtime.py`
  - Added `commander_router` stage event logging:
    - `route`: selected mode + agent chain
    - `transition`: runtime control (`retry/pause/cancel`) and status
    - `end`: final runtime mode/path/status
  - Added optional `state["event_logger"]` injection support.
  - Keeps fallback logger path using `EVENT_LOG_PATH` when injection is absent.

- File: `tests/test_m21_commander_runtime_entry.py`
  - Added tests that verify:
    - normal run emits `route -> end`
    - pause control emits `route -> transition -> end` and short-circuits node execution

## Safety Notes

- Existing decision/execution logic is unchanged.
- Logging failures are swallowed to avoid affecting runtime progression.
