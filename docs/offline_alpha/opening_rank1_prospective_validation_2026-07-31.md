# Opening Rank 1 Prospective Validation

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

## Evidence Gates

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
