# M31-7 Feature Engine and Regime Upgrade

- Date: 2026-03-07
- Goal: expand deterministic feature richness and improve regime classification with multi-factor context.

## Added

1. `libs/runtime/regime.py`
   - `classify_regime_v2(...)`:
     - uses `ma20_gap`, `volatility20`, optional `index_trend`, `realized_vol`,
       `global_sentiment`, `market_breadth`
     - emits `{regime, score, factors}`

2. `libs/runtime/feature_engine.py`
   - extended indicators (additive):
     - `ma60`, `ma120`, `ma60_gap`, `ma120_gap`
     - `adx14`
     - `gap_pct`
     - `vwap_distance`
     - `return20`
     - `rolling_drawdown20`
     - `regime_score`, `regime_factors`
   - cross-sectional enrichments in `build_feature_map`:
     - `cross_section_rank_signal`
     - `relative_strength20`
     - `sector_relative_strength`
     - `market_breadth`

3. `graphs/nodes/scanner_node.py`
   - passes context into `build_feature_map`:
     - `global_sentiment`
     - optional `market_context` values (`market_breadth`, `index_trend`, `realized_vol`)

## Compatibility

- existing feature keys remain unchanged
- all new fields are additive
- existing scanner and strategist contracts are preserved

## Tests

- `tests/test_strategy_feature_engine_upgrade.py`
  - extended feature fields are present
  - cross-sectional fields are produced
  - regime v2 reacts to realized volatility context
