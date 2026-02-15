# M21-2: Runtime Mode Resolution Policy

- Date: 2026-02-15
- Goal: define and enforce deterministic runtime mode routing for commander entry.

## Scope (minimal)

1. Add explicit mode resolution policy in runtime entry.
2. Allow env-based mode switch without changing caller code.
3. Keep default behavior backward-compatible.

## Implemented

- File: `graphs/commander_runtime.py`
  - Added `resolve_runtime_mode(state, mode=...)`.
  - Priority:
    1) explicit `mode` argument
    2) `state["runtime_mode"]`
    3) env `COMMANDER_RUNTIME_MODE`
    4) fallback `graph_spine`

- File: `graphs/nodes/commander_node.py`
  - Delegates mode selection to runtime policy.
  - Default remains `graph_spine` when no override is set.

- File: `tests/test_m21_commander_runtime_entry.py`
  - Added precedence and env-routing tests.

## Safety Notes

- No execution guard or risk policy logic changed.
- Existing behavior is preserved unless `runtime_mode`/env override is explicitly set.
