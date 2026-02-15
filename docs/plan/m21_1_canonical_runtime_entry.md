# M21-1: Canonical Commander Runtime Entry

- Date: 2026-02-15
- Goal: provide a single runtime entry for orchestration while keeping existing behavior unchanged.

## Scope (minimal)

1. Add canonical runtime entry function.
2. Keep default path backward-compatible (`graph_spine`).
3. Add unit tests for mode routing.

## Implemented

- File: `graphs/commander_runtime.py`
  - Added `run_commander_runtime(state, mode=...)` with two modes:
    - `graph_spine` -> `run_trading_graph`
    - `decision_packet` -> `decide_trade` -> `execute_from_packet`
  - Mode priority:
    - explicit argument
    - `state["runtime_mode"]`
    - fallback `graph_spine`

- File: `graphs/nodes/commander_node.py`
  - Switched to canonical runtime entry.
  - Preserved old behavior by pinning `mode="graph_spine"`.

- File: `tests/test_m21_commander_runtime_entry.py`
  - Added tests for:
    - default graph mode
    - decision packet mode routing
    - invalid mode fallback

## Safety Notes

- No execution guard or risk policy logic changed.
- Default runtime path remains graph spine to avoid behavioral drift.
