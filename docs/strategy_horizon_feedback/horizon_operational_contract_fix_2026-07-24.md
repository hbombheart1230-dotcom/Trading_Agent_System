# Horizon Operational Contract Fix

Date: 2026-07-24

## Decision

Strategy horizon is now an operational Commander-owned contract rather than
report-only metadata.

Strategist still proposes one of:

- `scalp`
- `intraday`
- `overnight_probe`
- `1_2day_swing`

Commander converts the proposal into a canonical policy. Monitor consumes that
policy for hold and exit timing.

## Defects Corrected

1. Long horizons were unconditionally downgraded to `intraday` during live
   validation.
2. Runtime artifacts said `observability_only=true` while some horizon
   translations already changed Monitor thresholds.
3. Monitor's default minimum hold could differ from the horizon report window.
4. Q9 could select a nested Strategist proposal instead of the authoritative
   Commander policy.
5. A new global strategy cycle could override the policy pinned to an already
   open position.
6. Overnight carry did not require an overnight-capable strategy horizon.
7. Persisted policies from the old observability deployment had no explicit
   migration path.

## Authoritative Flow

```text
Strategist horizon proposal
  -> Commander canonical horizon policy
  -> BUY fill pins policy to position_strategy_context
  -> Monitor applies the pinned policy
  -> Exit artifact records applied policy and alignment
  -> Q9/Q13 evaluation reads the Commander policy
```

For an open position, the BUY-time policy has priority over the current global
policy.

## Canonical Windows

| Horizon | min_sec | target_sec | max_sec |
| --- | ---: | ---: | ---: |
| `scalp` | 60 | 300 | 900 |
| `intraday` | 300 | 1,800 | 14,400 |
| `overnight_probe` | 1,800 | 14,400 | 86,400 |
| `1_2day_swing` | 3,600 | 86,400 | 172,800 |

`min_sec` blocks ordinary soft exits. It does not block hard stop, emergency,
broker/data integrity, or explicit hard invalidation exits.

`target_sec` is a reassessment and profit-management point. It is not a
guaranteed holding duration.

`max_sec` is the strategy time limit.

## Overnight Rule

Overnight carry is eligible only when all of the following are true:

- the pinned horizon is `overnight_probe` or `1_2day_swing`
- Commander behavior translation explicitly allows overnight
- independent PnL, trend, VWAP, liquidity, market, weekend, and holiday checks
  approve carry

An intraday horizon cannot become overnight solely because price action is
temporarily favorable.

## Compatibility

Old persisted Commander policies are normalized at runtime:

- the original horizon identity is retained
- the canonical window is restored
- operational authorization flags are added
- migration provenance is recorded

Historical reports are not rewritten to pretend the new behavior existed in
the past.

## Verification

Regression coverage verifies:

- canonical windows reach Monitor unchanged
- long horizons are not downgraded
- open-position policy beats a newer global policy
- Q9 prefers Commander policy over nested Strategist proposal
- legacy policies migrate without changing horizon identity
- intraday positions cannot receive overnight approval
- hard risk exits remain independent of the minimum hold
