# Horizon Alignment Decision

Date: 2026-06-22

Analysis range:

```text
2026-06-16 through 2026-06-22
```

Canonical generated report:

```text
reports/evaluation/decomposition/2026-06-22/horizon_alignment_review.md
```

## Fixed Promotion Contract

A time, tactic, and horizon combination is eligible for controlled-adoption
review only when all conditions pass:

- at least 20 forward observations
- at least 3 observed days
- maximum single-day share no greater than 60%
- maximum single-symbol share no greater than 40%
- conservative broker round-trip cost deducted
- average net return at least +0.30%
- net profit factor at least 1.20
- average net return remains positive when each observed day is excluded once

These thresholds are evaluation governance. They do not alter trading
behavior.

## Decision

```text
RETAIN_UNDER_OBSERVATION
```

There is no controlled-adoption candidate.

The only eligible combination with a positive average after cost was:

```text
open_20_60m | vwap_reclaim_pullback | +30m
```

Its evidence:

| Metric | Result |
| --- | ---: |
| Observations | 61 |
| Days | 5 |
| Symbols | 6 |
| Forward coverage | 55.96% |
| Average gross return | +1.0427% |
| Conservative round-trip cost | 0.9991% |
| Average net return | +0.0436% |
| Net win rate | 62.30% |
| Net profit factor | 1.0692 |
| Net maximum drawdown | -33.61% |
| Positive days | 3 of 5 |
| Worst leave-one-day-out net return | -0.6807% |

This is economically marginal and not robust. Removing either 2026-06-17 or
2026-06-22 makes the remaining average negative. The result therefore cannot
authorize a runtime change or a policy promotion.

## Rejected Interpretations

- The gross +1.0427% result is not a +1% trading edge. Almost all of it is
  consumed by the observed conservative round-trip cost.
- A 62.3% net win rate does not overcome the weak payoff distribution and
  drawdown.
- Strong `defensive_observe` aggregates are not actionable because their
  samples are concentrated in one or two days and symbols.
- Lane-level aggregates are diagnostic blocker classifications, not
  executable tactics, and cannot be promoted as policies.

## Next Evidence Rule

Keep this exact combination as a fixed shadow observation target. Do not add
new lanes or change its definition during the next bounded window.

The next review must end in one of two outcomes:

1. `PROMOTION_REVIEW_ELIGIBLE` if the fixed contract passes.
2. `REJECT` if it remains below the fixed contract.

No extension is authorized merely because the result is close to zero.

