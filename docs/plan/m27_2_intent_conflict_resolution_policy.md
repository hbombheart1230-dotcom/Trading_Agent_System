# M27-2: Intent Conflict Resolution Policy

- Date: 2026-02-20
- Goal: add deterministic conflict resolution for simultaneous multi-strategy intents.

## Scope (minimal)

1. Add policy module that resolves same-symbol opposite-side conflicts.
2. Add symbol-level concentration cap policy for intent overflow.
3. Add operator check script and regression tests.

## Implemented

- File: `libs/runtime/intent_conflict_resolver.py`
  - Added `resolve_intent_conflicts(...)`:
    - normalizes symbol/side and requested notional
    - resolves same-symbol BUY/SELL conflicts:
      - keep winning side by priority score
      - block opposite side with `opposite_side_conflict`
      - if tie, block all with `side_conflict_tie`
    - enforces per-symbol notional cap:
      - higher-priority intents kept first
      - overflow intents blocked with `symbol_notional_cap_exceeded`
  - Returns deterministic policy output:
    - `approved`, `blocked`, `blocked_reason_counts`, `approved_total`, `blocked_total`

- File: `scripts/run_m27_conflict_resolution_check.py`
  - Runs default scenario that must include both:
    - opposite-side conflict block
    - symbol cap overflow block
  - Exit code:
    - `0`: pass
    - `3`: fail
  - Supports failure injection via `--inject-fail`.

- File: `tests/test_m27_2_conflict_resolution.py`
  - opposite-side conflict regression
  - symbol cap enforcement regression
  - check script pass/fail regression
  - script file entrypoint import-resolution regression

## Notes for M27-3

- Next step should connect this resolver to allocation output from M27-1:
  - use strategy allocation budgets as upstream constraints
  - add commander/supervisor boundary integration check
