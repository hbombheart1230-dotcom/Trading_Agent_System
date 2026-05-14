# 2026-05-12 VWAP Exit Fresh Minute Source Hotfix

## Reason

003060 was bought and then sold almost immediately. The SELL was triggered by `vwap_breakdown` after about 32 seconds of actual holding.

The live artifact showed an inconsistency:

- Entry used fresh monitor minute data and accepted 003060 with VWAP distance around `+0.215%`.
- Exit saw current price and average price around `2,800 / 2,800`.
- Exit still triggered `vwap_breakdown` from `selected.features.engine_vwap_distance=-43.36%`.

That `selected.features` value can be stale scanner/feature context and should not override fresh per-symbol minute VWAP when evaluating an active position exit.

## Patch

- Monitor exit preview now computes fresh VWAP distance from `minute_ohlcv_by_symbol` for the held symbol when minute VWAP is available.
- Fresh minute VWAP distance overrides stale `selected.features.engine_vwap_distance` for exit policy input.
- Feature-based VWAP exit remains available only when fresh minute VWAP is unavailable.
- Exit policy now preserves the actual VWAP metric source in `exit_trigger_metric_source`.

## Validation

- `python -m py_compile graphs\nodes\monitor_node.py libs\runtime\exit_policy.py` passed.
- `.\venv\Scripts\python.exe -m pytest -q tests\test_monitor_exit_guard.py::test_monitor_vwap_breakdown_exit_uses_feature_signal tests\test_monitor_exit_guard.py::test_monitor_vwap_breakdown_exit_prefers_fresh_minute_vwap_over_stale_feature tests\test_monitor_exit_guard.py::test_monitor_peak_drawdown_respects_min_hold_guard` passed: 3 passed.
- `.\venv\Scripts\python.exe -m pytest -q tests\test_monitor_exit_guard.py` passed: 100 passed.
- `.\venv\Scripts\python.exe -m pytest -q tests\test_strategy_sizing_exit_upgrade.py::test_exit_policy_vwap_breakdown_triggers_with_profit_protection tests\test_strategy_sizing_exit_upgrade.py::test_exit_policy_cost_aware_floor_blocks_vwap_breakdown_on_small_profit tests\test_m29_3_monitor_exit_policy.py` passed: 19 passed.

## Live Check

Next exit artifacts should show `exit_trigger_metric_source` as `minute_ohlcv_by_symbol.vwap_distance` when fresh minute VWAP is present. Immediate VWAP exits should not be based only on stale scanner feature distance.
