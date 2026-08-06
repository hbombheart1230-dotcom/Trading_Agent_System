# Opening Rank-1 And Same-Symbol Sequence Review

## Questions

1. Did the system identify symbols that moved immediately or later?
2. Did downstream selection preserve the intrinsic Scanner signal?
3. Did repeated same-symbol trading give back an initially successful trade?
4. What evidence is still required before changing reentry behavior?

This document separates evidence collection from behavior changes.

## Opening Rank-1 Result

### Evidence coverage

| Population | Count |
|---|---:|
| Pre-Strategist intrinsic Rank-1 decisions | 65 |
| Deduplicated Rank-1 symbol-day events | 60 |
| Rank-1 events with complete D+5 | 51 |
| Same-decision Top-1 through Top-10 paths | 352 |
| Candidate paths with complete D+5 | 305 |

Every forward return includes a 0.28% round-trip cost assumption.

### Rank-1 versus alternatives

| Horizon | Paired decisions | Rank-1 minus lower-rank mean | Rank-1 better | Rank-1 worse |
|---|---:|---:|---:|---:|
| +30m | 52 | +0.5356%p | 32 | 20 |
| D+5 maximum high | 52 | +7.0242%p | 28 | 24 |
| D+5 close | 52 | +4.2769%p | 28 | 24 |

The Scanner's Rank-1 was not random. It had relative selection value against
the alternatives available at the same decision. Absolute D+5 Rank-1 close
was still -2.4310% on average, so automatic multi-day holding is not supported.

### Immediate expansion versus later reactivation

| Feature | Immediate +30m >= +5% | Initially non-positive, later +5% high |
|---|---:|---:|
| Cases | 3 | 8 |
| Average decision time after open | 6 seconds | 631 seconds |
| Average opening gap | +8.84% | +1.41% |
| Average entry versus prior close | +10.06% | +0.52% |
| Playbook | breakout 3 | pullback 5, defensive 3 |
| Average same-day close | +10.97% | -1.45% |
| Average D+5 close | +20.33% | -7.34% |

Among 19 D+5-complete Rank-1 cases with non-positive +30m:

- 8, or 42.11%, later reached a +5% high.
- 2, or 10.53%, retained at least +3% at the D+5 close.
- 6 of 8 later rallies were high-only opportunities that subsequently faded.

The common property is future attention and volatility. The entry mechanisms
are different. Opening expansion needs an immediate-continuation study. Later
reactivation needs a fresh-trigger study, not automatic holding.

## Current Same-Symbol Reentry Policy

The active control is implemented by
`libs/runtime/same_symbol_loss_reentry.py`.

```text
full same-day SELL
  -> realized return < 0
  -> store symbol/day LOSS
  -> hard-block that symbol for the rest of the Korean trading day
```

### Current behavior matrix

| Prior exit | Same symbol same day | Other symbol | Same symbol next day |
|---|---|---|---|
| Full realized loss | Blocked | Allowed | Allowed |
| Full profit or flat | Allowed | Allowed | Allowed |
| Partial loss exit | Allowed | Allowed | Allowed |
| Unknown PnL | Allowed and marked UNKNOWN | Allowed | Allowed |

The Monitor records `same_symbol_loss_reentry_control`, converts a loss state
to `same_symbol_loss_reentry_blocked`, and excludes only that symbol from the
runner-up cascade. Commander does not choose the replacement symbol.

Focused runtime tests cover state recording, same-day blocking, next-day
reset, partial exits, unknown PnL, entry guard behavior, and candidate cascade.

### Historical evidence that authorized the patch

| Cohort | Count | Win rate | Average return | Profit factor |
|---|---:|---:|---:|---:|
| First entry | 72 | 13.89% | -0.8506% | 0.3072 |
| All repeat entries | 27 | 3.70% | -1.2478% | 0.0026 |
| Repeat after a loss | 24 | 4.17% | -1.2756% | 0.0029 |
| Repeat after a non-loss | 3 | 0.00% | -1.0252% | 0.0000 |

Blocking loss-conditioned repeats was supported by 24 observations. Their
arithmetic cumulative return was approximately -30.61 percentage points.
This measures damage reduction, not positive alpha creation.

## The Remaining Gap: Profit Then Giveback

The current policy allows one more same-symbol trade after a profitable exit.
If that second trade loses, the new loss state blocks the third trade.

The three historical `repeat_after_non_loss` transitions are:

| Day | Symbol | Prior trade | Next trade | Current-policy relevance |
|---|---|---:|---:|---|
| 2026-06-08 | 052420 | +0.1700% | -1.1100% | Still allowed after first profit |
| 2026-07-02 | 038880 | +0.0894% | -0.5067% | Already prevented because the day's first trade was -0.6764% |
| 2026-07-10 | 005360 Monami | +1.7776% | -1.4589% | Still allowed after first profit |

The post-patch-relevant historical subset is therefore two sequences, not
three.

| Sequence | Stop after first profitable exit | Allow one repeat | Profit giveback |
|---|---:|---:|---:|
| 2026-06-08 052420 | +0.1700% | -0.9400% cumulative | 652.9% of first gain |
| 2026-07-10 Monami | +1.7776% | +0.3187% cumulative | 82.1% of first gain |
| Combined | +1.9476% | -0.6213% cumulative | 131.9% of combined gain |

The 052420 lifecycle has missing entry prices and unresolved rows, so it is
lower-quality evidence. The Monami sequence is cleaner:

1. The opening intrinsic Scanner Rank-1 had a virtual +16.3397% +30m path.
2. The first actual Monami trade entered at 09:57:02 and realized +1.7776%.
3. A second Monami trade entered at 10:11:47 and lost -1.4589%.
4. The day-symbol result remained slightly positive at +0.3187%, but 82.1% of
   the first realized gain was returned.

This is exactly the user's reported pattern. It is visible, but the clean
post-patch-relevant sample is only one strong case plus one lower-quality case.
A blanket profit-exit reentry ban is not yet evidence-complete.

## Required Artifacts

### 1. Same-symbol sequence ledger

Create one immutable row per day and symbol, updated by appended trade events:

`reports/evaluation/same_symbol_sequences/YYYY-MM-DD/same_symbol_sequence.json`

Required fields:

- `day_symbol_sequence_id`
- `symbol`, authoritative symbol name, point-in-time theme
- `trade_ordinal`
- entry/exit timestamps, prices, quantity, and broker order IDs
- realized gross return, broker cost, tax, slippage, and net return
- `prior_exit_outcome`
- cumulative day-symbol PnL before and after the trade
- first profitable exit amount
- profit giveback amount and giveback percentage
- maximum cumulative realized PnL and closeout PnL
- authoritative full/partial exit state and remaining broker quantity
- integrity status for malformed or unresolved timestamps

This prevents a collection of independent trade reports from hiding the fact
that the same symbol returned the first profit later in the day.

### 2. Reentry trigger provenance

Every second or later entry must preserve:

- prior exit timestamp, price, result, and reason
- seconds since prior exit
- prior Scanner decision ID and current Scanner decision ID
- prior setup episode ID and current setup episode ID
- `new_independent_episode` true/false/unknown
- price change since prior exit
- fresh VWAP reclaim, fresh high breakout, fresh volume confirmation
- market and theme state change since prior exit
- Strategist horizon and scenario change
- Monitor trigger and all failed checks
- guard decision and explicit override, if any

Without this artifact, a repeat caused by a genuinely new catalyst cannot be
separated from repeatedly trading the same exhausted move.

### 3. Reentry counterfactual shadow

Evaluate four policies from the same realized sequence:

| Policy | Meaning |
|---|---|
| CURRENT | Block only after a full realized loss |
| STOP_AFTER_FIRST_EXIT | Never reenter the symbol that day |
| FRESH_EPISODE_ONLY | Reenter only after a new independent setup |
| PROFIT_LOCK | Reentry allowed, but cumulative symbol profit cannot fall below a defined retained fraction |

Required outputs:

- accepted and blocked trade counts
- realized and counterfactual cumulative return
- avoided loss and missed upside
- win rate, expectancy, profit factor, and maximum drawdown
- first-profit retention ratio
- outcomes split by prior loss, flat, small win, and large win

No policy should be promoted from one Monami case. The shadow comparison makes
the next decision measurable without altering live behavior.

### 4. Rank-1 cross-day reactivation ledger

`reports/evaluation/opening_rank1_reactivation/YYYY-MM-DD/`

Required fields:

- original Rank-1 decision and stage lineage
- original +5m/+15m/+30m/+60m/EOD path
- D+1 through D+5 open/high/low/close and adjusted-price status
- timestamp of the future maximum high, not only its price
- future volume and turnover relative to the original day
- fresh VWAP/breakout/volume trigger timestamps
- intervening news and theme catalyst observed at that later timestamp
- sector and market-relative return
- lower-ranked same-decision control outcomes
- `high_only`, `durable_close`, `no_reactivation`, or `missing_evidence`

The timestamp and fresh trigger are essential. A D+5 high proves opportunity
existed but does not prove that the system could have entered before it.

### 5. Stage lineage completeness

For every Rank-1 decision, preserve one row containing:

- intrinsic Scanner Rank-1
- Strategist selected symbol and intrinsic symbol's post-Strategist rank
- Monitor candidate and entry intent
- Commander approve/reject and reason
- execution order ID or explicit no-order reason
- +30m outcome for every stage candidate

Only two historical executions currently link to the exact Q9 decision ID.
That is insufficient for a causal claim about which downstream agent lost the
opportunity.

## Decision Examples

### Example A: opening expansion

```text
09:00:06 Scanner intrinsic Rank-1 = Monami
09:01 reference price
+30m virtual result = +16.34%
```

The relevant question is whether immediate continuation was executable. D+5
holding is not needed to explain this opportunity.

### Example B: delayed reactivation

```text
09:17 Woojin Plaimm Rank-1
+30m = -0.45%
D+1 close = +2.09%
D+5 high/close = +7.94% / +3.89%
```

This is a plausible horizon-too-short case. It still needs a timestamped fresh
trigger before becoming a tradable reactivation policy.

### Example C: delayed high that should not be blindly held

```text
Techwing +30m = -4.40%
D+1 high/close = +17.51% / +9.08%
D+5 close = -23.31%
```

The symbol selection found future volatility, but holding through D+5 would
have been disastrous. A fresh-trigger exit-aware lane is required.

### Example D: first success followed by giveback

```text
Monami first actual trade = +1.7776%
Monami second actual trade = -1.4589%
day-symbol cumulative = +0.3187%
first-profit giveback = 82.1%
```

The current loss-reentry control permits the second trade and blocks only
after that loss. A profit-protection policy is therefore a separate hypothesis.

## Recommended Order

1. Keep the existing loss-reentry block unchanged.
2. Add the sequence ledger and reentry trigger provenance.
3. Run the four-policy counterfactual shadow on existing and future trades.
4. Add cross-day reactivation timestamps and fresh-trigger evidence.
5. Reassess after at least 10 clean profit-exit reentry opportunities or a
   materially larger historical reconstruction.

The immediate objective is not another hard rule. It is to distinguish:

- good symbol, good first trade, unnecessary repeat
- good symbol, valid new episode, profitable repeat
- good symbol, wrong original horizon
- volatile symbol whose future high was never practically capturable

Only then can profit protection and cross-day reactivation be promoted without
mixing separate phenomena.
