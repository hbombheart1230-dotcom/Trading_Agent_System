# Q12 BTC / Woori Technology Investment Baseline

## Purpose

Q12 is an independent shadow-only control that tests whether Bitcoin momentum
has measurable leading value for Woori Technology Investment (`041190.KQ`).

It does not replace or modify Q9, Q10, Q11, Strategist, Commander, Monitor, or
execution behavior.

## Inputs

- BTC/KRW when directly available, otherwise derived from `BTC-USD * KRW=X`
- BTC/USD from `BTC-USD`
- Coinbase proxy from `COIN`
- Crypto Fear & Greed Index from `alternative.me/fng`
- Woori minute candles from the existing Kiwoom minute provider

Unavailable BTC inputs are recorded as `btc_signal_unavailable`; they never
fall back to a fabricated neutral or positive signal.

The Crypto Fear & Greed Index is recorded as an observation-only feature:

- `crypto_fear_greed.value`
- `crypto_fear_greed.classification`
- `crypto_fear_greed.regime`
- `crypto_fear_greed.observed_at`
- `crypto_fear_greed.fallback_reason`

It does not change Q12 virtual entry eligibility in v0.

## Strategy v0

Entry requires all three conditions:

1. BTC 5-minute momentum is positive.
2. Woori has a volume spike or local breakout.
3. Woori is above VWAP or its 5-minute moving average.

The module records forward outcomes at +5m, +15m, +30m, and EOD. It does not
create an `OrderIntent`, submit an order, or alter portfolio state.

## Comparisons

- Q9 P/A/B/C
- Q10 Samsung/Hynix Top1
- Woori intraday buy-and-hold
- BTC momentum-only entries

All comparisons use the same broker cost profile and evaluation slippage.

## Artifacts

Stored under `reports/evaluation/baseline_btc_woori_tech/YYYY-MM-DD/`:

- `baseline_btc_woori_decisions.json`
- `baseline_btc_woori_forward_returns.json`
- `baseline_btc_woori_daily_report.md`
- `baseline_btc_woori_comparison.json`

## Governance

Q12 is evaluation-only. Promotion requires the standard evaluation and
promotion framework; a plausible narrative or one successful day is not
sufficient evidence.
