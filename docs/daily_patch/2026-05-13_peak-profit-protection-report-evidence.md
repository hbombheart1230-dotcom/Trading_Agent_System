# 2026-05-13 Peak Profit Protection / Report Evidence Alignment

## Context

- SK 034730 reached a strong intraday peak, then exited near breakeven after fees/tax.
- The earlier `max_hold` patch stopped time-limit exits from selling below the cost floor, but the remaining path still had gaps:
  - profit exits compared against account/effective PnL that already included cost drag
  - peak drawdown protection still waited for the generic confirmation count
  - held positions could inherit a newer strategy frame instead of the strategy captured at entry
  - trade reports could miss intermediate monitor events between entry and exit
  - recovered SELL-only lifecycle reports needed clearer partial/open/closed handling

## Patch

- Exit policy now separates gross profit from account/effective PnL:
  - `gross_pnl_ratio` / expected gross exit price drives profit-floor eligibility
  - account/effective PnL remains visible as cost-drag context
  - profit exits no longer double-count round-trip costs
- Peak drawdown urgent protection now overrides base confirmation to one tick.
  - When a position has already cleared the gross cost floor and then gives back enough from the peak, the monitor can sell immediately.
- Monitor exit policy now pins open-position exit controls to the strategy context captured when the position opened.
  - This prevents an intraday hold from suddenly receiving a later scalp `900s` frame.
- Trade report evidence now merges lifecycle run IDs with same-symbol monitor rows in the entry-to-exit time window.
  - Intermediate `monitor.threshold_snapshot`, `monitor.exit_decision_detail`, `monitor.state_transition`, and cycle events are available to the report.
- Recovered lifecycle handling was narrowed:
  - small SELL-only recovered lifecycles stay `partial`, but can still generate an explanatory AI report
  - runtime-state-enriched open snapshots can generate a diagnostic report
  - large recovered closeout SELL bundles at `1000` shares can be reconciled to closed when quantity evidence supports full liquidation

## Verification

- `.\venv\Scripts\python.exe -m pytest tests/test_strategy_sizing_exit_upgrade.py tests/test_monitor_exit_guard.py tests/test_m29_3_monitor_exit_policy.py tests/test_update_state_after_execution.py tests/test_live_execution_bundle_report.py tests/test_trade_regeneration_truth.py tests/test_trade_report_ai.py tests/test_operator_summary_reports.py -q`
- Result: `405 passed`.

## Live Check

- Confirm the next live reports show:
  - profit exits using gross/cost-floor fields, not only effective/account PnL
  - peak-drawdown exits firing without stale three-tick delay when urgent profit protection is armed
  - `position_strategy_context_applied=true` for exits from existing positions
  - report evidence includes the peak/high-water monitor event before the final SELL
  - recovered SELL-only trades are not mislabeled as closed unless quantity evidence supports full liquidation

