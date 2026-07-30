# Structural Alpha Batch 1 Result

## Decision

Batch 1 is closed.

| Hypothesis | Calibration +30m | Retrospective +30m | Decision |
| --- | ---: | ---: | --- |
| H4 Cross-Sectional Relative Strength | 160 observations, -0.1939%, PF 0.7492 | 167 observations, -0.5484%, PF 0.3664 | REJECT |
| H5 Point-in-Time Sector Leader | Not measurable | Not measurable | NOT_TESTABLE |
| H6 Volatility Contraction Breakout | 46 observations, -0.6059%, PF 0.2489 | 50 observations, -0.5746%, PF 0.2752 | REJECT |

H4 and H6 failed in both fixed evaluation splits after the 0.28% live cost
assumption. Neither hypothesis is eligible for threshold tuning, shadow
integration, or controlled adoption.

H5 was not backtested. Historical Q9 artifacts do not preserve point-in-time
sector membership and sector breadth. Applying the current sector mapping to
past dates would introduce look-ahead and survivorship bias.

## Fixed Contract

- Point-in-time universe: Q9 pre-Strategist Scanner Top 5
- Range: 2026-06-24 through 2026-07-30
- Calibration: 2026-06-24 through 2026-07-10
- Retrospective screening: 2026-07-13 through 2026-07-30
- Primary horizon: +30 minutes
- Cost: 0.28%
- Entry price: next available minute open
- Feature boundary: completed candles strictly before the decision minute
- Signal spacing: at most one signal per strategy every 15 minutes

July is already inspected data. A passing result would therefore have been
classified as `FUTURE_CONFIRMATION_REQUIRED`, not as production-ready alpha.

## Data Integrity

| Item | Result |
| --- | ---: |
| Raw Q9 Scanner windows | 12,783 |
| Canonical point-in-time windows | 12,382 |
| Invalid decision epochs excluded | 332 |
| Trading days | 27 |
| Unique symbols | 261 |
| Complete minute histories | 259 |

Two symbols were incomplete:

- `096610`: no historical minute rows returned
- `387690`: the earliest returned row was slightly later than its requested boundary

They appeared in two H4 episodes and one H6 episode. This does not alter the
decision: both hypotheses failed expectancy, profit factor, positive-day, and
drawdown gates by wide margins in both splits. The incomplete observations
remain visible in the machine-readable artifact rather than being silently
imputed.

## Gate Interpretation

H4 failed:

- calibration and retrospective forward-coverage gates
- calibration and retrospective expectancy gates
- retrospective profit-factor gate
- retrospective positive-day gate
- retrospective drawdown gate

H6 failed:

- retrospective forward-coverage gate
- calibration and retrospective expectancy gates
- retrospective profit-factor gate
- retrospective positive-day gate
- retrospective drawdown gate

Sample-count and concentration gates passing does not rescue a hypothesis with
negative net expectancy in both periods.

## Closed Actions

- Do not add H4 or H6 to live, shadow, Q9, or agent behavior.
- Do not create threshold variants of H4 or H6 under new hypothesis names.
- Do not infer H5 performance from current sector mappings.
- H5 can be evaluated only after a point-in-time sector membership and breadth
  collector has accumulated a separately defined future window.
- Batch 2 may test only the three predeclared structural hypotheses. It must not
  reopen Batch 1.

## Artifacts

- `reports/evaluation/offline_alpha/structural_alpha_batch1/2026-06-24_2026-07-30/structural_alpha_batch1.json`
- `reports/evaluation/offline_alpha/structural_alpha_batch1/2026-06-24_2026-07-30/structural_alpha_batch1.md`

This research changed no trading, shadow, order, Strategist, Scanner, Commander,
Monitor, or execution behavior.
