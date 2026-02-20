# M29-1 Feature Engine + Regime Scaffold

## Goal
- Add a minimal technical feature engine that can be attached to Scanner without breaking existing runtime contracts.
- Keep all new behavior optional and policy-driven (default impact is zero).

## Implemented
- Added `libs/runtime/feature_engine.py`.
- Implemented feature calculations from OHLCV series:
  - `rsi14`
  - `ma20` and `ma20_gap`
  - `atr14`
  - `volume_spike20`
  - `volatility20`
- Implemented regime classification:
  - `trend`
  - `range`
  - `high_volatility`
- Implemented signal output:
  - `signal_score` in `[-1, +1]`.

## Scanner Integration
- Updated `graphs/nodes/scanner_node.py` to consume feature inputs from:
  1. `state["scanner_features"]`
  2. `state["feature_engine"]["by_symbol"]`
  3. `state["ohlcv_by_symbol"]` (on-the-fly feature build)
- Added optional policy knobs:
  - `feature_score_weight` (default `0.0`)
  - `feature_risk_penalty` (default `0.0`)
  - `high_vol_risk_penalty` (default `0.0`)
  - `feature_trend_gap_threshold` (default `0.01`)
  - `feature_high_vol_threshold` (default `0.03`)
- Added scanner feature telemetry:
  - `state["scanner_feature"]` with `used/source/symbol_count/fallback/error_count`.

## Backward Compatibility
- Existing Scanner sentiment/skill behavior is unchanged by default because all feature weights default to `0.0`.
- Existing M18/M22 scanner tests remain valid.

## Tests
- Added `tests/test_m29_1_feature_engine.py`.
- Added `tests/test_m29_2_scanner_feature_integration.py`.
- Verified full suite:
  - `345 passed`.

