# M27-3: Portfolio Budget Boundary Guard

- Date: 2026-02-20
- Goal: connect M27-1 allocation output and M27-2 conflict resolver at commander/supervisor boundary.

## Scope (minimal)

1. Enforce strategy-level notional budgets from allocation output.
2. Apply conflict resolution and symbol concentration caps on budget-approved intents.
3. Add one boundary check script and regression tests.

## Implemented

- File: `libs/runtime/portfolio_budget_guard.py`
  - Added `apply_portfolio_budget_guard(...)`:
    - builds strategy budget map from M27-1 allocation output (`allocations[].allocated_notional`)
    - budget stage:
      - sorts intents by priority
      - blocks overflow with `strategy_budget_exceeded`
      - blocks invalid strategy/budget references (`missing_strategy_id`, `missing_strategy_budget`)
    - conflict stage:
      - calls M27-2 resolver (`resolve_intent_conflicts`)
      - applies opposite-side conflict and symbol cap policy
  - Returns unified output:
    - `approved`, `blocked`, `blocked_reason_counts`, `strategy_budget.usage`

- File: `scripts/run_m27_portfolio_budget_boundary_check.py`
  - Runs integrated scenario with all of:
    - strategy budget overflow
    - opposite-side conflict
    - symbol notional cap overflow
  - Exit code:
    - `0`: pass
    - `3`: fail
  - Supports failure injection with `--inject-fail`.

- File: `tests/test_m27_3_portfolio_budget_boundary.py`
  - budget overflow guard regression
  - integrated conflict+cap regression
  - boundary check script pass/fail regression
  - script file entrypoint import-resolution regression

## Notes for M27-4

- Next step should wire this boundary guard into canonical commander runtime path:
  - apply on candidate intents before final supervisor/executor handoff
  - include guard metrics/event log fields for operations visibility
