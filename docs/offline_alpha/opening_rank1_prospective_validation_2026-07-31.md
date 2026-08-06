# Opening Rank 1 Prospective Validation

## Program Identity

This program is not Q19. Q18 closed on 2026-07-30 as `RETAIN SHADOW`, and its
authority explicitly prohibited creating Q19 from that decision. This opening
study is an unnumbered, independent alpha-validation program:

`OPENING_ALPHA_VALIDATION_V1`

It may reuse Q9 evidence, but it does not reopen Q8-Q18 or continue their phase
counter. A passing result authorizes only the controlled shadow stage defined
below.

## Purpose

Validate the only bounded discovery candidate left by the June-July existing
evidence study:

`OPEN_0_20_RANK1_30M`

This is a prospective observation contract. It is not a trading strategy and
does not authorize an order.

## Frozen Cohort

- source: Q9 `scanner_pre_strategist_universe.intrinsic_ranked_top20`
- rank: exactly 1
- decision time: 09:00:00 through 09:19:59 KST
- repeated observation rule: at most one episode per symbol every 15 minutes
- reference entry: next available one-minute candle open
- forward horizons: +5m, +15m, +30m, +60m, EOD
- primary horizon: +30m
- live round-trip cost: 0.28%
- first eligible day: 2026-08-03
- 2026-07-31: implementation verification only and excluded

The cohort definition and thresholds must not be retuned during collection.

## Additive Opening Observability

The broad cohort remains unchanged. Each episode additionally preserves evidence
needed to explain the first seconds of an opening move:

- seconds from 09:00:00 to the Scanner decision,
- delay to the reference entry,
- opening price and reference-entry distance from the open,
- completed-bar count and completed cumulative volume at the decision,
- explicit `UNAVAILABLE_FIRST_MINUTE` state when no minute bar had closed,
- exact-opening, opening-chase, and late-no-chase subgroup labels,
- raw/pre-adjusted score, confidence, risk, sources, source scores, and score
  breakdown,
- compact quote snapshot, best bid/ask, and spread when Q9 retained them,
- explicit missing-field list for prior close, historical same-clock volume,
  upper-limit price, ask depth, and bid/ask evidence.

These fields are additive observation only. They do not change cohort membership,
promotion gates, orders, or runtime decisions. In particular, unfinished minute-bar
volume is never treated as point-in-time evidence.

## Evidence Gates

This section governs the frozen broad Rank-1 control cohort only. It is not the
five-session schedule for selecting the next narrow behavior-patch candidate. The two
timelines are reconciled in `canonical_execution_plan_2026-08-06.md`.

| Gate | Threshold |
| --- | ---: |
| +30m observed episodes | at least 25 |
| observed trading days | at least 10 |
| +30m forward coverage | at least 90% |
| +30m win rate | at least 50% |
| +30m average net return | greater than 0% |
| +30m profit factor | at least 1.20 |
| positive-day ratio | at least 55% |
| largest-day sample share | at most 25% |
| largest-symbol sample share | at most 25% |

Before the minimum evidence threshold, the status is `COLLECTING`.

After the minimum threshold:

- all quality gates pass: `ELIGIBLE_FOR_CONTROLLED_SHADOW`
- any quality gate fails: `REJECTED`

There is no automatic extension and no threshold adjustment after rejection.

## Authorized Next Stage

Passing the gates authorizes only a controlled shadow policy review.

It does not authorize:

- live entry
- live exit
- position sizing
- Scanner changes
- Strategist changes
- Commander changes
- Monitor changes
- order or execution changes

The controlled shadow stage may compare fixed +30m observation with a
structure-aware management simulation. It must not submit an `OrderIntent`.

## Artifacts

Daily:

`reports/evaluation/opening_rank1_shadow/YYYY-MM-DD/opening_rank1_shadow_daily.json`

`reports/evaluation/opening_rank1_shadow/YYYY-MM-DD/opening_rank1_shadow_daily.md`

Cumulative:

`reports/evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json`

`reports/evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.md`

The closeout maintenance flow regenerates both artifacts after market close.
It uses retained state candles first and requests fresh minute data only when
the retained candle history is incomplete.

## Separate Latent-Attention Observation

The retrospective longitudinal review found that 8 of 19 D+5-complete Rank-1
events with non-positive +30m returns later reached a +5% high. Only two retained
at least +3% through the D+5 close.

This is not part of the opening-expansion cohort and must not change its gates.
The two patterns remain separate:

- opening expansion: first seconds, breakout framing, immediate continuation
- latent attention: initial failure or fade followed by a fresh D+1 through D+5
  opportunity

Prospective artifacts may retain the failed Rank-1 symbol for a research-only
D+5 watch record. Any later observation must require a fresh timestamp and fresh
price/volume evidence. It does not carry the original entry forward, create an
overnight position, or authorize an order.

The detailed retrospective evidence is fixed in:

`docs/offline_alpha/opening_rank1_longitudinal_2026-07-31.md`
