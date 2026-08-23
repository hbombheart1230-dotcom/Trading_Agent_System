# Q14-Q18 Measurement Integrity Review - 2026-08-21

## Scope

This review changes evaluation and reporting only. It does not change Scanner,
Strategist, Commander, Monitor, entry, exit, order, or execution behavior.

## Findings And Corrections

| Phase | Finding | Correction | Historical impact |
| --- | --- | --- | --- |
| Q14 | `Scanner Ranking Failure` is outcome-conditioned, but the generated Q15 candidate used the largest behavior label. | Q15 candidate generation now uses the largest structural root cause. | The old Scanner-failure count remains descriptive. It cannot authorize a behavior patch. |
| Q13/Q14 Validation | Legacy `GO` required Scanner Ranking Failure on four of five days. | The result is explicitly scoped to diagnostic stability and sets `behavior_patch_authorized=false`. | Prior GO means the diagnostic repeated consistently, not that a Scanner patch was approved. |
| Q15 | The implemented patch restricted weak runner-up/candidate cascade selection. | No behavior change. Q15 is retained and compared with structural `Candidate Filtering` evidence. | Q15 remains directionally aligned with the corrected Q14 structural result. |
| Q16 | Forward rows had no explicit day-integrity contract. Numeric epoch strings could also be mistaken for `YYYYMMDD`. | Added KST timestamp parsing, baseline/checkpoint day validation, trusted and invalid counts. | The frozen Q16 `RETAIN` policy is not reopened. Post-close metrics are diagnostic only. |
| Q17 | Scalp evidence with expected horizon `+5m` was summarized primarily at `+15m/+30m`. | Added `+5m/+15m/+30m/+60m` tables and expected-horizon grouping. | Historical Q17 performance must be read at its intended horizon. Longer-horizon results are secondary diagnostics. |
| Q18 | Total observed rows/days were used as if they proved `+30m` coverage. | Added horizon-specific counts and day counts. Promotion requires verified `+30m` coverage. | Legacy Q18 aggregates without horizon counts are `LEGACY_HORIZON_COVERAGE_UNVERIFIED`, not promotion evidence. |

## Authoritative Q14 Reaggregation

For 2026-06-01 through 2026-08-21, the regenerated Q14 range contains 105
realized trades.

| Root cause | Kind | Trades | Interpretation |
| --- | --- | ---: | --- |
| Scanner Ranking Failure | outcome-conditioned | 22 | Losing aligned Top-1 observations; descriptive only |
| Candidate Filtering | structural | 17 | Largest actionable structural cause |
| Strategist Override | structural | 9 | Secondary structural cause |
| Missing Evidence | evidence gap | 54 | Repair observability; never treat as policy evidence |
| Aligned / No Alignment Issue | outcome-conditioned | 3 | Winning aligned observations; descriptive only |

The corrected Q15 candidate is therefore candidate/runner-up filtering, not a
Scanner score rewrite. This matches the Q15 behavior that was actually applied.

## Status Of Prior Evaluations

Prior artifacts are not deleted and the entire evaluation is not restarted.
They are divided into three authority classes:

1. **Retained policy evidence**: Q15 candidate filtering and Q16 proxy-only
   directional-evidence prohibition remain in force.
2. **Legacy diagnostic evidence**: Q14 outcome-conditioned counts and pre-v2 Q13
   timing may be used as descriptive history only.
3. **Unverified promotion evidence**: Q17 results evaluated at a horizon different
   from the intended horizon and Q18 aggregates without horizon-specific coverage
   cannot authorize promotion.

## Corrected Forward Evidence

- Q16 exact proxy-only rows: 899 total, 767 trusted, 132 legacy rows missing a
  baseline day.
- Q16 trusted `+30m` observations: 606 across 20 days; the frozen decision remains
  `RETAIN`.
- Q17 below-cost scalp candidates: 16 candidates, 14 observed at the intended
  `+5m` horizon.
- Q17 intended-horizon live-cost result: 64.29% win rate, +0.0557% average return,
  and 1.2692 profit factor. This is a small diagnostic sample, not promotion proof.
- Q18 post-reclaim history: 32 candidates and 31 generic observations across 18
  days, but legacy daily summaries do not prove any horizon-specific `+30m` count.
  The corrected status is `LEGACY_HORIZON_COVERAGE_UNVERIFIED`.

Prospective artifacts use these contracts:

- `q14_structural_causality.v2`
- `q13_q14_diagnostic_stability.v2`
- `q16_forward_integrity.v2`
- `q17_expected_horizon.v2`
- `forward_horizon_coverage.v2`
- `q18_horizon_coverage.v2`

## Decision Boundary

- Do not restart Q14-Q18 as new phases.
- Do not change trading behavior from this review.
- Preserve old reports as historical records, but do not mix them with v2
  prospective measurements without a cohort label.
- Any future promotion must use structural causality, trusted forward rows, the
  strategy's intended horizon, and horizon-specific sample/day coverage.
