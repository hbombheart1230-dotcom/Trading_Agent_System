# Q12 Five-Variable Hypothesis Validation

## Scope

- Validation and reporting only.
- Existing Q12 strategy behavior is unchanged.
- Q9, Q10, Q11, Scanner, Strategist, Commander, Monitor, and execution are unchanged.
- Candidate identity remains `BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1` under Alpha Research Board question B.

## Fixed Inputs

- BTC 08:55 KST 24-hour return thresholds: 3%, 4%, 5%, 7%.
- First surge versus repeated surge over the prior seven closed daily bars.
- BTC 20D, 60D, and ATH breakout state.
- Woori opening gap.
- Woori point-in-time price/volume confirmation at 09:03 and 09:05.

## Fixed Comparisons

- Entry: 09:00, 09:03, 09:05, 09:10, deterministic pullback.
- Forward: +5m, +15m, +30m, +60m, EOD.
- Metrics: sample count, win rate, average net return, MFE, MAE, profit factor, max drawdown.
- Cost: existing Q12 broker-cost profile plus existing evaluation slippage.

## Evidence Boundary

- `BACKCHECK`: through 2026-08-27.
- `PROSPECTIVE`: from 2026-08-28.
- The two phases are stored and aggregated separately.
- Missing point-in-time evidence is never inferred.

## Integration

- The Q12 runner creates daily and cumulative hypothesis artifacts.
- Frozen closeout invokes the same Q12 pipeline.
- Alpha Research Board reads the cumulative prospective `FAST_BUY_ALL_PASS` 09:05/+30m result into the existing question-B candidate.
- No new Board question or candidate ID was added.

## 2026-08-27 Backcheck Result

- Woori minute candles were recovered.
- Five entry methods and 25 forward checkpoints were computed.
- BTC 08:55 24-hour evidence remained missing because the exact prior-day point-in-time input was unavailable from the retained source window.
- The missing value was not replaced with the available 09:05 BTC observation.
