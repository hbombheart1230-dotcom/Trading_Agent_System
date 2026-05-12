# Minimal Multi-Position Patch Plan

## Status

Active design and first runtime patch as of 2026-05-08.

This replaces the two-slot runtime plan for now. The two-slot documents remain
as deferred design notes only and must not drive the next implementation.

First implementation scope has been applied to Commander, Monitor, and
candidate cascade:

- `RISK_MAX_POSITIONS` is resolved through runtime policy.
- default local live limit is `3`.
- same-symbol held-position BUY is blocked.
- same-symbol pending BUY is blocked.
- cascade may evaluate runner-ups when capacity remains.
- no slot-specific strategy/report split was added.

## Decision

Do not pre-assign trades into `short_term` and `long_hold` slots.

Keep the current trading flow:

- Strategist reads market, strategy, risk, scanner context, and recent runtime
  evidence.
- Strategist outputs entry/exit strategy guidance.
- Scanner ranks symbols according to that strategy frame.
- Monitor evaluates entry and exit timing from the selected candidates.
- Existing overnight/carry policy decides whether a held position can survive
  the close.

The minimal change is only:

- increase allowed active positions from 1 to a small number
- prevent duplicate same-symbol buys
- keep current risk, cost, closeout, and overnight controls

## Recommended Starting Limit

Start with `RISK_MAX_POSITIONS=3`.

Reason:

- It solves the current bottleneck where one held position blocks all new
  entries.
- It keeps order/execution/reporting complexity manageable.
- It gives enough room to observe whether the strategist/scanner/monitor flow
  can handle more than one open position.

Do not start at 5 unless 3-position live validation shows that:

- monitor exits all held positions coherently
- reports attribute fills and realized PnL correctly
- no same-symbol duplicates occur
- closeout and overnight carry decisions are clean

## Core Rule

New BUY is allowed only when all of these are true:

- current open position count is below `RISK_MAX_POSITIONS`
- selected symbol is not already held
- selected symbol does not have a pending BUY order
- daily loss, notional, quantity, cooldown, cost, closeout, broker truth, and
  data-quality guards pass
- monitor entry signal passes

New BUY is blocked when:

- `open_position_count >= RISK_MAX_POSITIONS`
- selected symbol is already held
- selected symbol has a pending BUY order
- any existing hard risk guard blocks entry

This means the old global `open_position_present` behavior should be narrowed
to max-position and same-symbol guards.

## What Stays The Same

Strategist:

- no forced slot selection
- no separate `short_term` / `long_hold` output required for the next patch
- continue producing market-aware entry/exit strategy guidance
- continue post-scanner selected-symbol refresh
- continue open-position refresh when Commander requests it

Scanner:

- same candidate ranking pipeline
- same candidate cascade concept
- no slot-specific candidate tree
- if the top candidate is already held or has pending BUY, Commander/Monitor
  should allow runner-up evaluation if capacity remains

Monitor:

- same entry signal logic
- same cost-aware entry filter
- same exit policy and profit-taking logic
- same hard stop and emergency exit priority
- same overnight/carry decision path

Reports:

- no slot folder split for the next patch
- add or preserve fields that make multi-position behavior auditable:
  - open position count at entry decision
  - max position limit
  - same-symbol duplicate block reason
  - pending BUY duplicate block reason
  - overnight carry decision, when evaluated

## Commander Ownership

Commander remains the final owner of runtime behavior.

Commander should normalize the current open-position gate into:

```json
{
  "multi_position_policy": {
    "enabled": true,
    "max_positions": 3,
    "same_symbol_reentry_allowed": false,
    "pending_buy_same_symbol_allowed": false,
    "open_position_gate_mode": "max_positions",
    "reason": "minimal_multi_position_without_slot_split"
  }
}
```

Commander must still prioritize:

1. emergency exit / broker truth mismatch
2. active position risk review
3. closeout and overnight carry review
4. new entries when capacity remains

The runtime may still emit at most one order intent per tick. That is
acceptable for the minimal patch.

## Open-Position Gate Change

Current behavior has several one-position assumptions:

- `monitor_only_when_holding`
- `block_buy_when_open_position`
- `open_position_present`
- candidate cascade blocked when `open_position_count > 0`
- pre-buy refresh skipped when any open position exists

For the minimal patch, reinterpret these as:

- monitor-only only when an existing position needs urgent review
- block BUY only when max positions reached or selected symbol is duplicate
- cascade may continue if there is remaining capacity
- post-scanner refresh remains mandatory for a selected fresh symbol
- pre-buy refresh may run while positions exist if capacity remains

## Same-Symbol Guard

Same-symbol duplicate protection is required because broker/account truth
merges lots by symbol.

Block a BUY when:

- symbol is already in broker positions with `qty > 0`
- symbol has a live pending BUY order
- symbol has a recent BUY intent that has not yet been reflected by broker
  truth

Allowed:

- SELL or risk-reducing action for an already held symbol
- monitor refresh for an already held symbol
- overnight carry review for an already held symbol

Not allowed for the minimal patch:

- scaling into the same symbol
- splitting one symbol into multiple strategy buckets
- averaging down as an independent behavior

## Overnight Policy

Do not create a separate long-hold lane now.

Existing overnight/carry policy remains the only path for carrying a position
past the close. The system can hold any position overnight only if the current
carry logic approves it.

If carry logic does not approve, the position should follow the existing
closeout/flatten policy.

## Implementation Boundary

First patch should implement only:

- `RISK_MAX_POSITIONS` support through the current runtime path
- open-position gate changed from global block to max-position block
- same-symbol held-position BUY block
- same-symbol pending BUY block
- cascade allowed when capacity remains
- observability fields in monitor/commander/report artifacts

First patch should not implement:

- two-slot ownership
- slot-specific folders
- slot-specific strategist JSON contract
- parallel scanner/monitor lanes
- same-symbol scaling
- memory-driven slot selection

## Validation Checklist

Live validation should answer:

- Does `RISK_MAX_POSITIONS=3` actually allow a second and third distinct
  symbol?
- Is same-symbol duplicate BUY blocked?
- If the top scanner candidate is already held, does the system evaluate the
  next candidate when capacity remains?
- Does monitor still exit held positions correctly?
- Does closeout still flatten when overnight carry is not approved?
- Do reports show why additional entries were allowed or blocked?

## Relationship To Deferred Two-Slot Design

The two-slot design is not deleted, but it is no longer the active path.

It may be revisited later if multi-position validation shows that the system
needs separate attribution by holding-period type. Until then, the active
runtime target is:

```text
one strategist/scanner/monitor flow
+ max 3 distinct held symbols
+ no duplicate same-symbol BUY
+ existing overnight/carry policy
```
