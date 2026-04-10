# Common Stock Only Universe Patch (2026-04-10)

## Goal
Temporarily exclude ETF / ETN / leveraged / inverse / active ETF products from the trading universe.
The current development and verification phase needs faster entry/exit feedback loops, and low-volatility ETF-style instruments were keeping holds open too long and masking exit validation quality.

## Policy Source Of Truth
Commander now owns the runtime universe policy.

Canonical policy path:
- `applied_policy.universe.asset_type = common_stock_only`

Current baseline:
- `common_stock_only`

This patch does not introduce a new env toggle.

## Runtime Structure
### 1) Scanner first-pass filter
`graphs/nodes/scanner_node.py` now applies an asset universe filter immediately after candidate collection and before practical scoring.

Behavior:
- Detects ETF/ETN-family instruments via metadata when available.
- Falls back to name heuristics when metadata is missing.
- Excludes detected ETF/ETN-family candidates from the scanner pool.

Representative exclusion classes:
- `etf`
- `etn`
- `leveraged_etf`
- `inverse_etf`
- `active_etf`
- `futures_etf`
- `covered_call_etf`
- `tr_index_product`

Representative heuristics:
- `ETF`
- `ETN`
- `레버리지`
- `인버스`
- `액티브`
- `선물`
- `TR`
- `커버드콜`

### 2) Final BUY guard at execution boundary
`graphs/nodes/execute_from_packet.py` now re-checks the asset universe policy before BUY execution.

Purpose:
- If scanner misses an ETF/ETN-family instrument, BUY execution is still blocked.
- SELL / EXIT paths remain allowed so existing positions can still be reduced or closed.

This keeps the architecture aligned with the current safety model:
- agents decide
- execution is gated
- final BUY blocking happens at the guard/execution boundary

## Observability
### Scanner surface
`scanner_output` and canonical `scanner.json` now expose:
- `asset_universe_policy`
- `asset_universe_policy_source`
- `excluded_candidate_count_by_asset_policy`
- `excluded_candidates_by_asset_policy`
- selected/ranked candidate asset hints when available

Scanner events now also emit:
- `scanner.asset_policy_exclusions`

Per-candidate exclusion rows include:
- `excluded_by_asset_policy`
- `exclusion_reason`
- `asset_class_detected`
- `detection_source`

### Final guard surface
When BUY is blocked by the final guard, execution/supervisor artifacts expose:
- `asset_universe_guard.excluded_by_asset_policy`
- `asset_universe_guard.exclusion_reason`
- `asset_universe_guard.asset_class_detected`
- `asset_universe_guard.detection_source`

## Compatibility
- Additive only
- Existing DTO/IO fields are not removed
- `reports/trades/*` structure is unchanged
- Single-position runtime posture is unchanged

## Known Scope Boundary
This patch enforces `common_stock_only` for detected ETF/ETN-family instruments.
If upstream metadata is missing and no name signal is available, the classifier may fall back to `unknown` rather than blocking blindly.
That is intentional for now to avoid false-positive blocks on common stocks.

## How To Re-expand Later
When asset universe expansion is needed again:
1. Change Commander baseline at `applied_policy.universe.asset_type`
2. Extend `libs/runtime/asset_universe_policy.py` classification rules
3. Keep scanner first-pass filtering and execution final guard aligned to the same policy path

The key rule is unchanged:
- one official policy path
- scanner filters first
- execution guard enforces last
