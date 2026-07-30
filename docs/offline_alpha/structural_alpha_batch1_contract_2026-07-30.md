# Structural Alpha Batch 1 Contract

## Boundary

This is an offline candidate-space screening study.

- no LLM
- no runtime graph
- no order intent
- no Scanner, Strategist, Commander, or Monitor behavior change
- no shadow integration from retrospective results alone

July 2026 has already been inspected by prior research. It is not an untouched
final holdout. A passing retrospective result can only become
`FUTURE_CONFIRMATION_REQUIRED`.

## Point-In-Time Universe

- source: Q9 pre-Strategist Scanner universe
- window type: `scanner_selection`
- ranks: Top 5
- range: 2026-06-24 through 2026-07-30
- invalid or synthetic epochs are excluded
- historical prices: Kiwoom `ka10080`
- one strategy signal at most every 15 minutes

## H4 Cross-Sectional Relative Strength

For every decision window:

1. Calculate each Top-5 symbol's trailing five-minute return.
2. Calculate current one-minute volume versus its prior ten-minute median.
3. Calculate current one-minute turnover.
4. Rank the three values within the point-in-time Top-5 universe with equal
   weight.
5. Select the highest composite candidate only when its five-minute return is
   positive and its price is above session VWAP.

No threshold grid is allowed.

## H5 Sector Leader

Required evidence:

- point-in-time sector or theme membership
- point-in-time sector breadth and return
- point-in-time member ranking

The current artifacts retain `sector_relative_strength` for only a small June
subset and do not retain historical sector membership. Current theme API data
must not be backfilled into historical dates.

Fixed outcome when the required evidence is absent:

`NOT_TESTABLE_MISSING_POINT_IN_TIME_SECTOR_MEMBERSHIP`

This is a data-contract result, not a failed strategy result.

## H6 Volatility Contraction Breakout

For every Top-5 candidate:

1. Mean candle range of the latest five completed minutes must be at most 75%
   of the prior fifteen-minute mean range.
2. Current close must exceed the prior ten-minute high.
3. Current one-minute volume must be at least 1.5 times the prior ten-minute
   median.

When multiple candidates qualify, select the one with the largest breakout
distance.

No threshold grid is allowed.

## Evaluation

- calibration: 2026-06-24 through 2026-07-10
- retrospective check: 2026-07-13 through 2026-07-30
- horizons: +5m, +15m, +30m, +60m, EOD
- primary horizon: +30m
- live cost: 0.28%
- maximum next-print delay: 180 seconds

Research-candidate gates:

- calibration observations at least 15
- retrospective observations at least 25
- +30m coverage at least 90% in both splits
- live-net expectancy positive in both splits
- retrospective PF at least 1.20
- retrospective positive-day ratio at least 55%
- retrospective MDD no worse than -6%
- largest day share at most 30%
- largest symbol share at most 40%

Outcomes:

- `FUTURE_CONFIRMATION_REQUIRED`
- `REJECT`
- `NOT_TESTABLE_MISSING_POINT_IN_TIME_SECTOR_MEMBERSHIP`

There is no automatic extension or threshold relaxation.
