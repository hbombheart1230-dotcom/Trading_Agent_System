# M31-11 Feature/Regime Phase-1 Upgrade

- Date: 2026-03-07
- Scope: additive upgrade of deterministic feature and regime inputs.

## What Changed

1. `libs/runtime/feature_engine.py`
- Added `trend_strength` (signed ADX-derived trend magnitude).
- Added `realized_volatility` output field.
- Added `cross_section_rank` alias while preserving `cross_section_rank_signal`.
- Added context alias support for `realized_volatility` in `build_feature_map`.

2. `libs/runtime/regime.py`
- Added `realized_volatility` alias input (kept `realized_vol` compatibility).
- Kept multi-factor regime classification deterministic.
- Added explicit volatility penalty component in trend score computation.
- Extended factor payload:
  - `realized_volatility`
  - `market_breadth_centered`
  - `volatility_penalty`

3. `graphs/nodes/scanner_node.py`
- Exposed additional engine features in scan output:
  - `engine_ma60`, `engine_ma120`
  - `engine_adx14`, `engine_trend_strength`
  - `engine_realized_volatility`
  - `engine_vwap_distance`, `engine_rolling_drawdown20`
  - `engine_sector_relative_strength`
  - `engine_cross_section_rank`

## Compatibility

- No DTO/IO contract break.
- No raw event schema change.
- Existing keys preserved.
- New fields are additive and optional for downstream consumers.

## Validation

- Updated tests:
  - `tests/test_strategy_feature_engine_upgrade.py`
  - `tests/test_m29_2_scanner_feature_integration.py`
- Full test suite green after patch.

