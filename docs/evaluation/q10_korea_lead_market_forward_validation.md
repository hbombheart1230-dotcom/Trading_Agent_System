# Q10 Korea Lead-Market Forward Validation

Program ID: `Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION`

Activation date: `2026-08-31`

## Purpose

This experiment tests one fixed question prospectively:

> Do the prior US night market and the 08:50 KST futures/FX snapshot contain
> forward edge for Samsung Electronics, SK Hynix, KOSPI, and KOSDAQ after
> the Korean market opens?

It extends the Q10 family but does not replace or alter the existing
Samsung/Hynix ranking baseline. It is observation-only and cannot create an
`OrderIntent` or call the Executor.

## Frozen Inputs And States

The immutable preopen snapshot records prior-session SOX, Nvidia, Micron,
SK Hynix ADR when available, Nasdaq, S&P 500, US 10Y and VIX, plus the 08:50
Nasdaq 100 futures, S&P 500 futures and USD/KRW observations. It also records
the prior SK Hynix return and its trailing three-session cumulative return.

SK Hynix and Samsung states:

- `STRONG_POSITIVE`
- `POSITIVE`
- `NEUTRAL`
- `NEGATIVE`
- `STRONG_NEGATIVE`

Korean index states:

- `STRONG_RISK_ON`
- `RISK_ON`
- `NEUTRAL`
- `RISK_OFF`
- `STRONG_RISK_OFF`

SOX candidate thresholds are frozen at `+3%`, `+5%`, `-3%`, and `-5%`.
Confirming Nvidia/Micron/ADR observations raise confidence. Opposing Nasdaq
futures and adverse USD/KRW lower confidence. Samsung applies a lower SOX
sensitivity (`0.65`) than SK Hynix. An absolute SK Hynix trailing three-day
move of at least `8%` is tagged `EXTENDED`; otherwise it is `FIRST_MOVE`.

Samsung-specific HBM, foundry, earnings, or guidance news is tagged
`SAMSUNG_SPECIFIC_EVENT` and excluded from the pure lead-market comparison.

These thresholds must not change during the validation cohort.

## Daily Flow

1. The Q10 shadow loop starts independently before market open.
2. The opening macro collector records an additional fixed `08:50` slot.
3. Between 08:50:00 and 08:59:59 KST, Q10 captures its lead-market snapshot
   once and never overwrites it.
4. If that window is missed, the day is marked `MISSED`; later data must not
   be used to reconstruct a fake 08:50 snapshot.
5. During the session, current-day minute candles and Kiwoom index snapshots
   populate 09:00, 09:03, 09:05, 09:10, 09:15, 09:30, 10:00 and close.
6. At close, Q10 calculates opening gap, forward return, MFE, MAE and the
   expected-versus-actual reaction class.
7. Shadow-only 09:00/09:03/09:05/09:10 entries are compared. For an
   `OVERREACTION`, the first `0.5%` pullback before 10:00 is also evaluated.
8. Daily and prospective cumulative reports apply the same Q10 cost/slippage
   assumptions. No result is connected to execution.

## Reaction Classes

- `UNDERREACTION`: actual gap is less than half the frozen expected magnitude.
- `FAIR_REACTION`: actual gap is in the expected band.
- `OVERREACTION`: actual gap exceeds 1.5 times the expected magnitude.
- `DIVERGENCE`: actual direction conflicts with the expected direction.

Neutral expectations use a separate `0.5%` fair-gap band.

## Artifacts

Daily directory:

`reports/evaluation/baseline_samsung_hynix/YYYY-MM-DD/q10_forward_validation/`

- `q10_preopen_signal_snapshot.json`
- `q10_actual_market_reactions.json`
- `q10_expected_vs_actual.json`
- `q10_shadow_entry_comparison.json`
- `q10_forward_validation_report.md`

Prospective cumulative file:

- `reports/evaluation/baseline_samsung_hynix/q10_forward_validation_cumulative.json`

The cumulative reader rejects days before `2026-08-31`. It separates Samsung
specific-event observations and SK Hynix `FIRST_MOVE`/`EXTENDED` observations.

## Validation Report Example

```markdown
# Q10 Korea Lead-Market Forward Validation

- Day: `2026-08-31`
- Preopen snapshot: `CAPTURED`
- Mode: `prospective_shadow_only`

| Target | Expected | Opening Gap | Classification | Bucket |
|---|---|---:|---|---|
| sk_hynix | STRONG_POSITIVE | 1.10% | FAIR_REACTION | LEAD_MARKET_SIGNAL |
| samsung | POSITIVE | 0.20% | UNDERREACTION | LEAD_MARKET_SIGNAL |

| Target | Entry | Trades | Win Rate | Avg Net | MFE | MAE |
|---|---|---:|---:|---:|---:|---:|
| sk_hynix | ENTRY_0905 | 1 | 100.00% | 0.62% | 1.30% | -0.22% |
```

The example describes structure only. It is not a forecast or a historical
result.

## Implementation Boundary

Implementation modules:

- `forward_validation/contracts.py`: immutable experiment contract
- `forward_validation/market_inputs.py`: point-in-time lead-market provider
- `forward_validation/scoring.py`: explainable fixed-rule states
- `forward_validation/reaction_reader.py`: Korean market checkpoint reader
- `forward_validation/expected_actual.py`: gap reaction classification
- `forward_validation/shadow_comparison.py`: non-executable entry comparison
- `forward_validation/cumulative.py`: prospective-only aggregation
- `forward_validation/report.py`: Markdown rendering
- `forward_validation/pipeline.py`: artifact orchestration

The parent Q10 pipeline only invokes this adapter and returns its artifact
paths. A measurement failure is isolated and cannot stop the original Q10
baseline report.
