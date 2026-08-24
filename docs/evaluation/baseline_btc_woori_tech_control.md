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

It did not change Q12 virtual entry eligibility in v0. Starting with decision
policy `q12_btc_multihorizon_leading_signal.v2`, it remains observation-only
and is not itself an entry condition.

## Strategy v2

Entry requires all three conditions:

1. BTC multi-horizon leading momentum is confirmed.
2. Woori has a volume spike or local breakout.
3. Woori is above VWAP or its 5-minute moving average.

The BTC leading condition passes when either:

- BTC 5-minute momentum is positive; or
- the 60-minute/24-hour regime is bullish, 15-minute momentum is positive,
  and the current 5-minute pullback is greater than `-0.30%`.

This separates a shallow pause inside a strong BTC trend from an actual sharp
short-horizon reversal. The artifacts retain the legacy 5-minute result as
`positive`, and record the v2 result as `leading_positive` with an explicit
`leading_signal_reason`.

The module records forward outcomes at +5m, +15m, +30m, and EOD. It does not
create an `OrderIntent`, submit an order, or alter portfolio state.

## Strong BTC Rise Shadow Variant

Starting after the 2026-08-24 review, the existing v2 series remains intact and
an additive shadow policy is recorded as
`BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1`.

The variant requires all of the following:

1. BTC has risen at least `1.0%` over 60 minutes or `3.0%` over 24 hours.
2. The multi-horizon leading signal is still positive; a sharp 5-minute decline
   is not hidden by the longer trend.
3. Woori confirms locally through volume spike or breakout and remains above
   VWAP or MA5.

This isolates the historically promising `strong_bull` subgroup from the broad
BTC bull condition that failed day-concentration review. It is a new prospective
shadow comparison, not a relabeling or promotion of the rejected broad rule.
Its metrics are written under `policy_variant_summaries` in the forward artifact.

## Comparisons

- Q9 P/A/B/C
- Q10 Samsung/Hynix Top1
- Woori intraday buy-and-hold
- BTC momentum-only entries

All comparisons use the same broker cost profile and evaluation slippage.

## Historical v1/v2 Review

Run the deterministic replay with:

```powershell
.\venv\Scripts\python.exe scripts/run_q12_historical_policy_review.py
```

The replay reads only stored Q12 decisions and forward returns. It does not
fetch replacement history or create execution intent. Consecutive v2-only
signals within 30 minutes are counted as one episode using the first signal.

The 2026-06-25 through 2026-08-21 replay produced 19 independent v2-only
episodes. At +30 minutes, the real-account cost assumption (`0.28%`) produced
a 68.4% win rate and +0.5329% average return. This is a promising subset, not
production authorization; prospective v2 shadow evidence remains required.

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
