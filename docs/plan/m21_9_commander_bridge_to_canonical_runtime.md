# M21-9: Legacy Commander Bridge to Canonical Runtime

- Date: 2026-02-15
- Goal: reduce duplicate orchestration risk by giving legacy `Commander` users a direct path to canonical runtime.

## Scope (minimal)

1. Add a bridge method on `Commander` to call canonical runtime entry.
2. Keep existing `Commander.run()` behavior unchanged.
3. Add tests for bridge path and transition handling.

## Implemented

- File: `libs/agent/commander.py`
  - Added `Commander.run_canonical(...)`:
    - forwards to `graphs.commander_runtime.run_commander_runtime(...)`
    - supports `mode`, `graph_runner`, `decide`, `execute` injections
  - Existing `run(...)` contract is unchanged.

- File: `tests/test_commander_contract.py`
  - Added bridge tests:
    - graph mode route via injected runner
    - pause transition short-circuit behavior

## Safety Notes

- Legacy flow remains default (`run(...)`).
- Bridge enables staged migration to one canonical runtime without forced refactor.
