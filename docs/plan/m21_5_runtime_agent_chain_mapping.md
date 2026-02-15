# M21-5: Runtime Agent Chain Mapping

- Date: 2026-02-15
- Goal: codify canonical agent routing order in runtime state for observability and consistency.

## Scope (minimal)

1. Define agent-chain mapping by runtime mode.
2. Expose mapping in runtime output without changing existing execution behavior.
3. Add unit tests to lock expected chain order.

## Implemented

- File: `graphs/commander_runtime.py`
  - Added mode-specific runtime chain mapping:
    - `graph_spine`:
      `commander_router -> strategist -> scanner -> monitor -> supervisor -> executor -> reporter`
    - `decision_packet`:
      `commander_router -> strategist -> supervisor -> executor -> reporter`
  - Added `runtime_plan` state annotation on each run:
    - `runtime_plan.mode`
    - `runtime_plan.agents`

- File: `tests/test_m21_commander_runtime_entry.py`
  - Added assertions for `runtime_plan` in:
    - default graph mode
    - decision packet mode
    - pause transition short-circuit path

## Safety Notes

- No transition or guard policy changed.
- Runtime behavior remains identical; this patch adds structured mapping metadata only.
