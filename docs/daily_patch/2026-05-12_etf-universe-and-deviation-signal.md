# 2026-05-12 ETF Universe And Deviation Signal

## Context

- Operator requested removing the ETF/ETN family block and reflecting ETF/NAV deviation.
- Target behavior: discount deviation (`dstr_rt` negative) can support entry, premium deviation (`dstr_rt` positive) can support exit.

## Changes

- Default universe policy changed from `common_stock_only` to `all_tradable`.
- Explicit `common_stock_only` still blocks ETF/ETN products at scanner and executor guards.
- Added shared ETF deviation utility:
  - Reads `etf_deviation_pct` / `nav_deviation_pct` / Kiwoom `dstr_rt` from quote raw payloads and propagated features.
  - Keeps missing/blank deviation neutral.
- Scanner now records and scores ETF deviation:
  - Negative deviation adds a small candidate bias.
  - Positive deviation adds a small risk/confidence penalty.
- Monitor entry now supports `etf_discount_reversion_path`:
  - Requires discount signal plus chart sanity: VWAP/reclaim structure, extension control, and confirmation.
  - Does not blindly buy solely because deviation is negative.
- Monitor exit now supports `etf_premium_take_profit`:
  - Positive deviation can trigger exit.
  - Cost-aware profit floor is still respected.

## Validation

- `venv\Scripts\python.exe -m pytest -q tests/test_asset_universe_policy.py tests/test_execute_from_packet.py::test_execute_from_packet_blocks_buy_when_asset_universe_policy_rejects_etf tests/test_execute_from_packet.py::test_execute_from_packet_blocks_buy_when_remote_symbol_profile_identifies_etf`
  - 22 passed
- `venv\Scripts\python.exe -m pytest -q tests/test_intraday_monitor_signals.py::test_intraday_entry_allows_etf_discount_reversion_path tests/test_strategy_sizing_exit_upgrade.py::test_exit_policy_etf_premium_take_profit_uses_deviation_signal tests/test_strategy_sizing_exit_upgrade.py::test_exit_policy_etf_premium_take_profit_respects_cost_floor`
  - 3 passed
- `venv\Scripts\python.exe -m pytest -q tests/test_intraday_monitor_signals.py tests/test_strategy_sizing_exit_upgrade.py`
  - 98 passed
- `venv\Scripts\python.exe -m pytest -q tests/test_m29_3_monitor_exit_policy.py`
  - 17 passed

## Runtime Notes

- Kiwoom quote payload exposes `dstr_rt`, but sampled ETF quotes sometimes return it blank.
- When blank, the system still allows ETF candidates but deviation scoring remains neutral.
- Live validation should check whether real-time quote cycles populate `dstr_rt` for ETF/ETN symbols.
