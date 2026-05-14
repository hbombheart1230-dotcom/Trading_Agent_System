# 2026-05-13 Operator Summary Pattern Performance

## Context

- The current system already has individual trade evidence in `ai_trade_summary.md`.
- Strategist detail is available through `strategist_summary`.
- Memory remains disabled for trading decisions until the strategist/scanner/monitor stack is more stable.
- The missing first step was a visible, auditable aggregate layer that shows which strategy/scanner/monitor patterns are winning or losing.

## Change

- Added `pattern_performance` to operator summaries:
  - `reports/operator_summary/daily/*/daily_summary.json`
  - `reports/operator_summary/weekly/*/weekly_summary.json`
  - `reports/operator_summary/monthly/*/monthly_summary.json`
  - `reports/operator_summary/symbols/*/symbol_summary.json`
- Added a concise `Pattern Performance` markdown section to the matching summary `.md` files.
- Daily summaries now merge `daily_report.trade_index` with same-day symbol trade history by `trade_id`, so pattern performance keeps richer fields such as hold time and normalized pattern context when the daily trade index is thinner.
- Placeholder patterns such as `hold`, `unknown`, and recovered-entry boilerplate are not counted as real entry/exit patterns.
- The aggregation remains observation/reporting only. It does not enable strategy memory, scanner memory, or monitor memory feedback.

## Aggregated Axes

- Strategist:
  - final playbook
  - tactical strategy
  - strategy horizon
  - risk tone
  - trade aggressiveness
  - candidate watch rank/cascade policy
- Scanner:
  - selected rank bucket
  - selection basis
  - scanner chart-fit bucket
  - scanner chart-fit authority
  - commander candidate-watch effect
- Monitor entry:
  - entry pattern
  - human chart entry score bucket
  - candle quality bucket
  - VWAP reference quality bucket
  - reward-room score and reward-room percent bucket
  - late-entry risk
- Monitor exit:
  - exit pattern
  - exit reason
  - cost-floor state
  - peak-drawdown state
  - time-limit reassessment state
  - VWAP breakdown observation state
  - monitor exit-triggered state
- Combined:
  - tactical strategy + scanner rank + entry pattern + exit pattern

## Files

- `libs/reporting/operator_period_summary.py`
- `tests/test_operator_summary_reports.py`

## Validation

- `python -m py_compile libs/reporting/operator_period_summary.py`
- `python -m pytest tests/test_operator_summary_reports.py -q`

Result: `19 passed`.

## Follow-Up

- After one or two full sessions, review the new `Pattern Performance` section before enabling any memory-driven bias.
- If the section becomes too noisy, keep the JSON full-detail and trim markdown to the top 2-3 most useful axes.
