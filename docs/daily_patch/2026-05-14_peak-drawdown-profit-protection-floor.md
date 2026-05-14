# 2026-05-14 Peak Drawdown Profit Protection Floor

## Summary

- `peak_drawdown` exit is now treated as profit protection only.
- In `profit_protection` mode, peak drawdown is armed only after max run-up crosses the effective profit floor.
- The effective floor includes the cost-aware floor: `round_trip_cost_floor_pct + min_net_profit_buffer_pct` or the configured `cost_aware_profit_floor_pct`, whichever is larger.

## Behavior

- If the peak never crossed the profit floor, drawdown from peak can be recorded but cannot trigger a sell.
- The monitor now exposes:
  - `peak_drawdown_armed`
  - `peak_drawdown_blocked`
  - `peak_drawdown_block_reason`
  - `peak_drawdown_profit_floor_required_pct`
  - `peak_drawdown_profit_floor_met`
- Loss handling remains separate through hard stop, stop loss, VWAP breakdown, and structure invalidation paths.

## Verification

- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py -q`
- `venv\Scripts\python.exe -m pytest tests\test_strategy_sizing_exit_upgrade.py tests\test_monitor_candidate_cascade.py tests\test_intraday_monitor_signals.py tests\test_m22_skill_native_scanner_monitor.py tests\test_monitor_exit_guard.py -q`

