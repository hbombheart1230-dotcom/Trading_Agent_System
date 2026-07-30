# Structural Alpha Batch 2 Result

## Decision

Batch 2 is closed.

| Hypothesis | Calibration +30m | Retrospective +30m | Decision |
| --- | ---: | ---: | --- |
| H7 Market Shock Relative-Strength Reversal | 30 observations, +0.1583%, PF 1.1952 | 38 observations, -0.0657%, PF 0.9280 | REJECT |
| H8 Oversold Mean Reversion | 58 observations, -0.0372%, PF 0.9440 | 53 observations, -0.8934%, PF 0.2797 | REJECT |
| H9 Trend Pullback Resumption | 66 observations, -0.4552%, PF 0.3754 | 85 observations, -0.4285%, PF 0.3767 | REJECT |

All results include the fixed 0.28% live cost assumption.

H7 did not generalize from calibration to the retrospective period. Its
retrospective expectancy, profit factor, positive-day ratio, drawdown, and
coverage all failed.

H8 and H9 had negative net expectancy in both periods. H9 had sufficient
forward coverage in both periods, so its rejection is not a missing-data
artifact.

## Data Integrity

| Item | Result |
| --- | ---: |
| Canonical point-in-time windows | 12,382 |
| Trading days | 27 |
| Historical symbols complete | 259/261 |

The two incomplete histories are the same known provider gaps documented in
Batch 1. The failures are wide enough that imputation cannot make any strategy
eligible. Missing outcomes remain missing and are reflected in coverage.

## Closed Actions

- Do not add H7, H8, or H9 to live, shadow, Q9, or agent behavior.
- Do not tune the fixed thresholds against the inspected July outcomes.
- Do not extend the observation period automatically.
- Do not create renamed variants of these hypotheses.

## Artifacts

- `reports/evaluation/offline_alpha/structural_alpha_batch2/2026-06-24_2026-07-30/structural_alpha_batch2.json`
- `reports/evaluation/offline_alpha/structural_alpha_batch2/2026-06-24_2026-07-30/structural_alpha_batch2.md`

This research changed no trading, shadow, order, Strategist, Scanner, Commander,
Monitor, or execution behavior.
