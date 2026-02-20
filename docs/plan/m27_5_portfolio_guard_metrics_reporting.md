# M27-5: Portfolio Guard Metrics Reporting

- Date: 2026-02-20
- Goal: expose runtime portfolio guard behavior as daily operator metrics.

## Scope (minimal)

1. Aggregate `portfolio_guard` summary payload from commander events.
2. Add report fields including blocked reason TopN.
3. Add one operator check script and regression tests.

## Implemented

- File: `scripts/generate_metrics_report.py`
  - Added `portfolio_guard` metrics block:
    - `total`
    - `applied_total`
    - `approved_total_sum`
    - `blocked_total_sum`
    - `blocked_reason_total`
    - `blocked_reason_topN`
  - Reads `payload.portfolio_guard` from `stage=commander_router` events.
  - Added Markdown section `## Portfolio Guard`.
  - Added empty-report defaults for the same keys.

- File: `scripts/run_m27_portfolio_guard_metrics_check.py`
  - Seeds deterministic commander events with `portfolio_guard` payload.
  - Generates daily metrics report and validates:
    - `applied_total >= 1`
    - `blocked_total_sum >= 1`
    - `blocked_reason_topN` contains `strategy_budget_exceeded`
  - Exit code:
    - `0`: pass
    - `3`: fail
  - Supports failure injection with `--inject-fail`.

- File: `tests/test_generate_metrics_report.py`
  - Added portfolio guard aggregation regression.
  - Added empty metrics report key regression for `portfolio_guard`.

- File: `tests/test_m27_5_portfolio_guard_metrics_report.py`
  - Added check script pass/fail regressions.
  - Added script file entrypoint import-resolution regression.

## Notes for M27-6

- Next step should add alert policy hooks for portfolio guard anomalies:
  - high blocked ratio on guard-applied runs
  - repeated `strategy_budget_exceeded` spikes by day
