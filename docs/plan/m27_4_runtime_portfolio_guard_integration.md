# M27-4: Runtime Portfolio Guard Integration

- Date: 2026-02-20
- Goal: wire M27 portfolio guard to canonical graph runtime path and surface guard summary in commander events.

## Scope (minimal)

1. Integrate portfolio guard node into graph execution flow.
2. Keep default behavior backward-compatible (guard disabled unless configured).
3. Add runtime integration check script and regression tests.

## Implemented

- File: `graphs/nodes/portfolio_guard_node.py`
  - Added runtime node that:
    - reads `state["intents"]`
    - applies `apply_portfolio_budget_guard(...)` when enabled
    - updates:
      - `state["intents"]` (approved only)
      - `state["portfolio_guard"]` summary
      - `state["blocked_intents"]` details
    - clears `state["selected"]` if all intents are blocked
  - Activation:
    - `use_portfolio_budget_guard=true`, or
    - explicit budget/allocation config in state

- File: `graphs/trading_graph.py`
  - Wired `portfolio_guard_node` after `monitor` and before `decision`.
  - Applies in initial pass and retry loop.
  - Keeps injection support via new `portfolio_guard=` parameter.

- File: `graphs/commander_runtime.py`
  - Added commander `end` event payload summary for portfolio guard:
    - `portfolio_guard.applied`
    - `portfolio_guard.approved_total`
    - `portfolio_guard.blocked_total`
    - `portfolio_guard.blocked_reason_counts`

- File: `scripts/run_m27_runtime_portfolio_guard_check.py`
  - Runs integrated graph scenario and verifies all key guard reasons:
    - `strategy_budget_exceeded`
    - `opposite_side_conflict`
    - `symbol_notional_cap_exceeded`
  - Exit code:
    - `0`: pass
    - `3`: fail
  - Supports failure injection via `--inject-fail`.

- File: `tests/test_m27_4_runtime_portfolio_guard_integration.py`
  - graph wiring regression
  - commander end event guard-summary regression
  - runtime check script pass/fail regressions
  - script file entrypoint import-resolution regression

## Notes for M27-5

- Next step should expose portfolio guard metrics in daily metrics report:
  - `portfolio_guard_applied_total`
  - `portfolio_guard_blocked_total`
  - `portfolio_guard_blocked_reason_topN`
