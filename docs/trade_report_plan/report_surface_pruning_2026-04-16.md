# Report Surface Pruning Plan (2026-04-16)

## Goal

Reduce report sprawl without regressing the stabilized trade report path.

This slice does not redesign reporting.
It removes low-value default outputs first.

## Current Principle

Do not prune by folder name alone.
Prune by actual runtime ownership and code consumption.

## Keep

These remain active because they are either source-of-truth, operator-critical, or still consumed by trade report/runtime paths.

- `reports/canonical`
- `reports/trades`
- `reports/daily/<day>`
- `reports/metrics`
- `reports/dev/analysis/reporter_analysis`
- `reports/dev/analysis/live_execution_bundles`
- `reports/live_summary`
- `reports/live_watch`

## Disable By Default

These are currently low-value operator surfaces and are not required for the stabilized trade report path.

- `reports/decision_story`
- `reports/run_cards`

Current action:

- `scripts/run_mock_exam_day.py` closeout no longer generates them by default
- manual generation remains available through:
  - `scripts/run_decision_story_report.py`
  - `scripts/run_run_card_report.py`

## Hold For Later Review

These are still coupled enough that they should not be removed in the same slice.

- `reports/dev/analysis/trade_explain`
  because reporter feedback still reads it
- `reports/dev/analysis/reporter_analysis`
  because same-day trade linkage and operator UI still read it

## Why The Recent Trade Report Work Is Safe

The recent trade report work depends on:

- `lifecycle_bundle.json`
- `ai_trade_report_input.json`
- `ai_trade_report.json`
- `ai_trade_report.md`
- `report_generation_state.json`
- same-day reporter linkage

It does not require `decision_story` or `run_cards` to be auto-generated in closeout.

## Next Safe Pruning Order

1. disable `decision_story` and `run_cards` by default
2. unify live and batch trade-report runtime behind one shared service
3. reassess whether `trade_explain` is still needed as a generated artifact
4. only then shrink the remaining `reports/dev/*` surface
