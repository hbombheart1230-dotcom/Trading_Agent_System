# Structural Alpha Batch 2 Contract

## Boundary

- Research only
- No live, shadow, order, agent, or execution behavior change
- Point-in-time universe: Q9 pre-Strategist Scanner Top 5
- Range: 2026-06-24 through 2026-07-30
- Calibration: 2026-06-24 through 2026-07-10
- Retrospective screening: 2026-07-13 through 2026-07-30
- Primary horizon: +30 minutes
- Cost: 0.28%
- At most one signal per strategy every 15 minutes
- Features use completed candles strictly before the decision minute
- Entry uses the next available minute open
- July is not an untouched final holdout

This is the final predeclared structural batch. Threshold variants are not new
hypotheses and are prohibited after results are inspected.

## H7 Market Shock Relative-Strength Reversal

Market proxies:

- `069500` KODEX 200
- `229200` KODEX KOSDAQ 150

The market return is the mean available 15-minute return of the two proxies.

All conditions must hold:

1. market 15-minute return is at or below -0.75%
2. candidate 5-minute return is positive
3. candidate is above session VWAP and current volume is at least 1.2 times
   the prior 10-minute median

Selection: highest candidate return minus market return.

## H8 Oversold Mean Reversion

All conditions must hold:

1. 14-period RSI is at or below 30
2. current completed close is above the previous completed close
3. current volume is at least the prior 10-minute median

Selection: lowest RSI, then highest one-minute rebound.

## H9 Trend Pullback Resumption

All conditions must hold:

1. 5-minute SMA is above the 20-minute SMA and the 20-minute SMA is rising
2. the previous close was at or below its 5-minute SMA and the current close
   has reclaimed the current 5-minute SMA
3. the current close is above the previous high and current volume is at least
   the prior 10-minute median

Selection: largest 5-minute SMA premium over the 20-minute SMA.

## Fixed Gates

- calibration observed count >= 15
- retrospective observed count >= 25
- forward coverage in each split >= 90%
- net expectancy in each split > 0
- retrospective profit factor >= 1.20
- retrospective positive-day ratio >= 55%
- retrospective maximum drawdown >= -6%
- retrospective largest single-day share <= 30%
- retrospective largest single-symbol share <= 40%

Possible outcomes:

- `FUTURE_CONFIRMATION_REQUIRED`
- `REJECT`

There is no automatic observation extension. A failure is closed without
threshold tuning.
