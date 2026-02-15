# M21-6: Canonical Runtime Once CLI (Safe Smoke Default)

- Date: 2026-02-15
- Goal: provide a single automation entry that can execute the canonical commander runtime once, with offline-safe default behavior.

## Scope (minimal)

1. Add one CLI entry for commander runtime once execution.
2. Default to safe smoke mode (no real provider/execution path).
3. Support runtime mode and runtime transition flags.
4. Add tests for JSON output contracts.

## Implemented

- File: `scripts/run_commander_runtime_once.py`
  - New CLI options:
    - `--mode {graph_spine,decision_packet}`
    - `--runtime-control {retry,pause,cancel}`
    - `--live` (real node path)
    - `--json`
  - Default path is offline smoke with stub runners.
  - Emits compact summary fields:
    - `runtime_mode`, `runtime_status`, `runtime_transition`, `runtime_agents`, `path`, `execution_allowed`

- File: `tests/test_m21_runtime_once_script.py`
  - Added coverage for:
    - default smoke (`graph_spine`)
    - decision packet smoke path
    - pause transition short-circuit output

## Safety Notes

- Default CLI mode is smoke (offline-safe).
- Real node execution path requires explicit `--live`.
