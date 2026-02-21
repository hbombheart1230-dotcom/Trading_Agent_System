# M27-6: Portfolio Guard Alert Policy

- Date: 2026-02-20
- Goal: detect portfolio-guard stress conditions via alert policy thresholds.

## Scope (minimal)

1. Extend alert threshold gate with portfolio guard signals.
2. Add operator check script for pass/fail scenarios.
3. Update env/runbook/docs for new threshold controls.

## Implemented

- File: `scripts/check_alert_policy_v1.py`
  - Added thresholds:
    - `portfolio_guard_blocked_ratio_max`
    - `portfolio_guard_strategy_budget_exceeded_max`
  - Added warning alert codes:
    - `portfolio_guard_blocked_ratio_high`
    - `portfolio_guard_strategy_budget_exceeded_high`
  - Added corresponding output values and thresholds in JSON result.

- File: `scripts/run_m27_portfolio_guard_alert_policy_check.py`
  - Seeds deterministic events with `commander_router.end.payload.portfolio_guard`.
  - Runs alert policy check in `--fail-on warning` mode.
  - Verifies pass/fail cases and expected alert codes.
  - Exit code:
    - `0`: check script pass
    - `3`: check script fail

- File: `tests/test_m27_6_portfolio_guard_alert_policy.py`
  - blocked ratio warning regression
  - strategy-budget-exceeded spike warning regression
  - check script pass/fail regressions
  - script file entrypoint import-resolution regression

- File: `docs/runtime/alert_policy_runbook.md`
  - Added new threshold env vars and triage items.

- File: `config/.env.example`
  - Added commented env examples for M27-6 threshold controls (single canonical template).

## Notes for M27-7

- Next step should connect these alerts into scheduled ops batch notification policy:
  - portfolio-guard warning grouping
  - noise-control tuning for repeated guard alerts
