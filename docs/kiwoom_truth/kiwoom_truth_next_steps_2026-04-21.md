# Kiwoom Truth Next Steps (2026-04-21)

## Goal

Close the remaining broker-truth gaps without widening runtime risk.

Current priority is:

1. reduce `ambiguous_symbol_rows`
2. improve first-write live report truth
3. keep fallback paths explicit and honest

## Priority 1: Ambiguous Day-PnL Matching

Current weak cases:

- repeated same-symbol intraday trades
- same `symbol + filled_qty + filled_price`
- missing or late entry-side fill recovery

Development target:

- add a conservative tie-breaker when multiple `ka10077` rows survive exact symbol/qty/sell-price matching
- use existing runtime evidence only:
  - trusted entry fill when present
  - monitor/account snapshot implied buy basis when available
- do not promote ambiguous rows to authoritative unless the tie-breaker is clearly unique

Success criteria:

- fewer `broker_day_match_mode = ambiguous_symbol_rows`
- more `broker_day_authoritative = true`
- no silent optimistic promotion

## Priority 2: First-Write Live Truth

Current status:

- regenerated reports are much stronger
- live first-write is improved but must keep matching regenerated quality

Development target:

- ensure first-write trade artifacts preserve:
  - entry order id
  - entry fill price
  - exit fill price
  - day-pnl truth when exact matching is possible

Success criteria:

- next live trade should not need regeneration to show:
  - `broker_buy_price`
  - `broker_fill_price`
  - `broker_realized_pnl`
  - `broker_fee`
  - `broker_tax`

## Priority 3: Honest Fallback Surface

When authoritative broker truth is still not available:

- keep `reference_only`
- keep `broker_fill_account_snapshot_estimate`
- keep source labels explicit

Do not collapse estimate and truth into one surface.

## Not in this slice

- broad fee/tax model redesign
- orderable-cash redesign
- new report sections
- non-deterministic matching heuristics

## Immediate implementation order

1. conservative ambiguous-row tie-breaker
2. targeted regression tests for repeated same-symbol trades
3. artifact validation on the next live trades
