# Horizon Slot One-Symbol Policy

## Status

HOLD / deferred design-only policy note.

As of 2026-05-08, this is not the active implementation path. The active path
is `multi_position_minimal_patch_plan_2026-05-08.md`.

No runtime behavior is changed by this document. Keep it only as a historical
design alternative in case slot attribution is revisited later.

Do not implement or use the two-slot rules below unless the slot design is
explicitly reactivated. The current live path is not slot-based.

## Decision

The system should use exactly two holding-period slots:

- `short_term`: max 1 active symbol
- `long_hold`: max 1 active symbol

`short_term` combines the current scalp and intraday behavior. It should keep
the existing scanner, chart, VWAP, volume, monitor timing, cost filter, and
exit logic as-is until a separate patch explicitly changes it.

`long_hold` covers overnight, 1-2 day, and multi-day holding ideas. It should
be evaluated separately from `short_term` because the entry reason, hold
reason, exit reason, and report review are different from current short-term
trading.

The account may hold at most two active symbols:

- one symbol owned by `short_term`
- one symbol owned by `long_hold`

The same symbol must not be opened in both slots at the same time.

Example:

- Allowed: `short_term=005930`, `long_hold=000660`
- Blocked: `short_term=005930`, `long_hold=005930`

This policy is holding-period based, not tactical-strategy based.

## Non-Goal

Do not create one live position slot per tactical strategy.

These tactical labels must not become independent capacity buckets:

- `opening_gap_momentum`
- `opening_range_breakout`
- `volume_breakout`
- `leader_vwap_reclaim_pullback`
- `reversal_reclaim`
- `cost_aware_scalp`
- `defensive_observe`

Also do not create separate capacity for the legacy raw hold-horizon labels:

- `scalp`
- `intraday`
- `overnight_probe`
- `1_2day_swing`

Those labels may still appear as raw strategist hints or report history, but
runtime capacity should collapse them into:

- `scalp` / `intraday` -> `short_term`
- `overnight_probe` / `1_2day_swing` / multi-day hold -> `long_hold`

## Rationale

The current runtime mostly behaves as a global one-position short-term system.
Once an open position exists, Commander, Monitor, and cascade logic tend to
clamp fresh candidate exploration with reasons such as `open_position_present`.

That makes it hard to test longer-hold ideas without interfering with the
current short-term trading loop.

The two-slot design keeps the current short-term behavior intact while adding
one separate long-hold lane. This is simpler than four slots and matches the
actual operational question:

- Is the current chart-driven short-term system working?
- Can a separate longer-hold system improve results without mixing attribution?

## Symbol Uniqueness Rule

Initial implementation should enforce account-wide symbol uniqueness across
the two slots.

Reason: the broker account represents the same symbol as one merged position.
If both slots buy the same symbol, average price, quantity, realized PnL, and
exit attribution become ambiguous.

Initial rule:

- If a symbol is already active in any slot, the other slot must reject a new
  BUY intent for that symbol.
- The active slot remains responsible for managing and closing that symbol.
- Cross-slot same-symbol scaling is out of scope until broker-truth attribution
  and per-lot accounting are explicitly designed.

## Required Runtime Shape

Each candidate, intent, order, open position, and report artifact should carry
a stable slot identifier:

```json
{
  "horizon_slot": "short_term|long_hold",
  "strategy_horizon": "short_term|long_hold",
  "source_strategy_horizon": "raw strategist horizon or hold hint"
}
```

`horizon_slot` is the operational capacity bucket. `strategy_horizon` is the
Commander-approved operating horizon. `source_strategy_horizon` preserves the
Strategist proposal when Commander maps, caps, or adjusts it.

## Guard Model

The slot guard should check both slot capacity and account-wide risk:

- Slot capacity: max 1 active symbol per `horizon_slot`
- Symbol uniqueness: no same symbol across active slots
- Global risk: daily loss, total notional, broker truth mismatch, emergency
  closeout, and account-level risk limits still override both slots
- Carry risk: urgent exit review may temporarily suppress new entries across
  both slots

This means `RISK_MAX_POSITIONS` cannot remain the only live-position gate if
both slots are enabled. It should either be raised to 2 or wrapped by a
slot-aware guard.

## Initial Rollout Recommendation

Implementation should be staged, but the target live shape is two slots:

1. Preserve current `short_term` behavior.
2. Add observability fields:
   - `horizon_slot`
   - `slot_occupancy`
   - `slot_block_reason`
   - `same_symbol_cross_slot_blocked`
3. Add `long_hold` selection and management as a separate path.
4. Let both slots trade in mock investment mode after the slot guard and report
   attribution are visible.

## Reporting Requirement

Daily, weekly, monthly, and symbol reports should show results by holding slot:

- trades count
- win rate
- gross return
- net return after fee/tax
- average hold time
- main entry pattern
- main exit pattern
- same-symbol cross-slot rejections
- slot capacity rejections

Without this split, the system may look like one low-win-rate strategy even
when one holding period works and the other does not.

## Implementation Impact Estimate

This is not an env-only change.

Expected implementation areas:

- Strategist and Commander: map raw horizon hints into `short_term` or
  `long_hold`
- Scanner and cascade: evaluate candidates only for available slots
- Monitor: block only occupied slot entry, not all fresh entries
- Supervisor/risk: enforce two-slot capacity and same-symbol uniqueness
- Executor/truth reconciliation: persist slot metadata with orders and fills
- Runtime memory/state: restore active slot ownership after restart
- Reports: aggregate by slot
- Tests: slot occupancy, same-symbol block, restart recovery, report summaries

Approximate scope:

- design and observability only: 0.5 day
- two-slot live mock guard and attribution: 1-2 days
- robust long-hold management and restart recovery: 3-5 days

## Open Questions Before Coding

- Should `long_hold` open fresh symbols directly, or only convert a strong
  short-term winner into a longer-hold position?
- Should the two slots split notional evenly, or should Commander allocate more
  budget to the slot with better recent net performance?
- Should a slot enter cooldown after a stop loss, and should that cooldown be
  slot-only or account-wide?
