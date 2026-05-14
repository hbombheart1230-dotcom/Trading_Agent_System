# 2026-05-13 Chart Positive Entry And Cooldown Scope

## Context

- Today no-trade flow was not caused by chart feature calculation being absent.
- Scanner already applied `entry_compatibility_bias` and `scanner_macro_chart_fit_bias`, but the monitor's weighted chart score was still mostly shadow/observability.
- Many waits clustered around `below_vwap_reclaim_not_ready`, and post-exit cooldown could still suppress all new symbols when the last sell symbol was not considered.

## Patch

- Strengthened scanner compatibility bias when recent monitor blocks are dominated by VWAP reclaim failures.
  - `below_vwap_reclaim_not_ready` / `pullback_below_vwap_reclaim_not_ready` with ratio >= 45% now uses bias scale `0.16`.
  - Volume-confirmation dominant blockers keep existing `0.15`, but move to `0.18` when ratio >= 60%.
  - `pullback_not_mature` / `breakout_not_ready` with ratio >= 45% now uses bias scale `0.14`.
- Fixed scanner blocker-context sampling so position `hold` statuses do not mask real entry blockers.
  - Recent monitor artifacts now use `entry_candidate_cascade.reason` / `top_pick_reason` before generic `primary_reason_code`.
  - Non-runtime test directories under `reports/canonical/<day>` are ignored by the bias-context sample.
- Added selective live promotion for strong human-chart A setups.
  - Allows BUY promotion only when candle quality, VWAP reference quality, reward room, multi-window structure, extension safety, and exit risk all pass.
  - Only minor legacy misses are overrideable: `rebound_ok`, low-but-acceptable `entry_chart_score`, confidence not confirmed, and legacy path near-ready.
  - Still does not bypass volume-missing, no reward room, high late-entry risk, strong VWAP breakdown, swing-low break, or exit-risk blockers.
- Scoped post-exit cooldown to the sold symbol when `persisted_state.last_trade_symbol` is available.
  - If AAA was just sold, BBB can still be evaluated and bought.
  - If legacy state has no last trade symbol, existing global cooldown behavior remains as fallback.

## Verification

- `venv\\Scripts\\python.exe -m py_compile libs\\runtime\\intraday_monitor_signals.py graphs\\nodes\\scanner_node.py graphs\\nodes\\monitor_node.py`
- `venv\\Scripts\\python.exe -m pytest tests/test_intraday_monitor_signals.py tests/test_scanner_monitor_compatibility.py tests/test_monitor_exit_guard.py`
- Result: `183 passed`

## Live Check Focus

- Confirm `human_chart_entry_setup_applied=true` appears only on clean A setups.
- Confirm `human_chart_buy_guard` still blocks upper-limit/no-reward-room late entries.
- Confirm after a sell, cooldown blocks only the same symbol when `last_trade_symbol` is present.
- Confirm scanner selected rows show non-zero `entry_compatibility_bias` / `scanner_macro_chart_fit_bias` and stronger reclaim-dominant bias scale.
