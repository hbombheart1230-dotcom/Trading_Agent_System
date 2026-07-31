# 2026-07-31 Scanner Market Candidates and Q11 Index Sanity

## Incident

The market showed strong opening moves, but the main scanner did not surface them in time.

Observed causes:

- Kiwoom market sources returned broad data, but the final candidate pool collapsed to 6-8 symbols after theme filtering.
- The reduced pool was filled with up to five Strategist backfill symbols.
- A partial `scanner_features` cache could return early and leave newly introduced candidates without hydrated features.
- Q11 used an unconfirmed KOSPI200 mock snapshot above +16% as a trusted market return. This distorted symbol relative strength.

## Changes

### Scanner candidate ownership

- Theme selection no longer removes candidates sourced from:
  - `top_value`
  - `top_volume`
  - `top_change_rate`
  - `condition_search`
  - `operator_watchlist`
- Theme filtering still applies to theme-only candidates.
- Avoid-theme and downstream risk, cost, entry, and execution guards remain unchanged.
- Scanner artifacts now expose:
  - `market_native_bypass_count`
  - `market_native_bypass_symbols`

This preserves the architecture in which Strategist context can influence ranking but cannot erase native market leaders from the Scanner universe.

### Scanner feature hydration

- A partial direct feature cache is no longer treated as complete.
- Cached features are retained.
- Only missing candidate symbols are hydrated.
- Hydrated and cached feature maps are merged deterministically.

### Q11 market-index sanity

- The raw KOSPI200 move remains stored as `kospi200_pct_raw`.
- A KOSPI200 warning with `requires_confirmation=true` sets:
  - `kospi200_trusted=false`
  - scoring input `kospi200_pct=null`, normalized to a neutral 0% reference
  - `market_data_quality_reason`
- Symbol relative strength records whether it used:
  - `kospi200`
  - `market_neutral_fallback`

Q11 remains shadow-only. No order or main execution behavior was added.

## Unchanged

- Scanner score thresholds
- Monitor entry and exit conditions
- Cost floor
- Commander risk veto
- Order and execution flow
- Q9/Q13/Q14 attribution formulas

## Runtime Verification

After restart:

- Main candidate pool: 34
- Strategist backfill count: 0
- Native source counts included top-value, top-volume, and top-change-rate rows
- Main runtime heartbeat advanced and stderr remained empty
- Q11 regenerated successfully
- Q11 KOSPI200:
  - raw: 17.65%
  - trusted: false
  - scoring reference: 0%
- Q11 Samsung Electro-Mechanics relative strength:
  - open return: +1.241135%
  - relative strength: +1.241135%
  - reference: `market_neutral_fallback`

## Tests

- Focused regression: 35 passed
- Scanner/Q9/opportunity regression: 148 relevant tests passed; one legacy US-symbol policy test was updated to the current Korean universe contract
- Full regression before that fixture update: 2,379 passed, 1 legacy fixture failed

The legacy diversification fixture used `AAPL/MSFT` in the Korean live scanner. It now uses Korean symbols and neutral scanner features so the test measures diversification policy rather than asset-universe rejection.
