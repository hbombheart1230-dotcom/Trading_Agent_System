# Stage-2 Candidate Authority Review And Stability Correction

Date: 2026-08-27

## Scope

This change completes the existing Agent Effectiveness evaluation for the
post-Scanner Strategist refresh. It does not change Scanner scoring, Monitor
entry/exit rules, Commander risk rules, order execution, or the Strategist LLM
prompt/model.

## Exact Cumulative Review

Authority artifacts:

- `reports/evaluation/agent_effectiveness/cumulative_20260601_20260827/strategist_stage2_authority_review.json`
- `reports/evaluation/agent_effectiveness/cumulative_20260601_20260827/strategist_stage2_authority_review.md`

The review is rebuilt as exact daily shards and deduplicated by Q9 decision ID.
This avoids loading the 3.8 GB historical Q9/shadow input set into memory at
once. Only refresh windows with a directly linked Stage-2 response are eligible
for a Stage-2 authority decision.

| Authority | Comparable | Days | Average Delta | State |
|---|---:|---:|---:|---|
| all refresh pipeline, diagnostic only | 1,073 | 12 | -0.0459%p | `OBSERVATIONAL_ONLY` |
| Stage-2 rerank | 230 | 11 | -0.3752%p | negative signal; promotion stability pending |
| Stage-2 candidate change | 124 | 8 | -0.6960%p | negative signal; promotion stability failed |
| entry tightening | 372 observed | 12 | -0.3356% candidate cohort | `NOT_MEASURABLE` |
| no-trade recommendation | 21 observed | 5 | -0.2979% candidate cohort | `NOT_MEASURABLE` |

Entry tightening and no-trade do not have an explicit downstream adoption trace
and untreated paired control. Their cohort returns cannot authorize an authority
change.

## Stability Recheck

The first review treated material paired degradation as sufficient for an
advisory-only runtime patch. A concentration audit showed that this was not a
safe promotion decision:

- 106 of 124 comparable candidate changes occurred on 2026-08-26 and
  2026-08-27.
- the largest day contributed 56.5% of candidate-change comparisons.
- only 4 of 8 days had a negative daily average.
- the mean was affected by extreme paired deltas, while the median was only
  -0.2214 percentage points.

The negative result remains a valid diagnostic signal, but it is not stable
enough to reduce production authority. The candidate replacement clamp was
removed before deployment. Stage-2 behavior remains unchanged.

Promotion eligibility now requires all of the following in addition to the
existing materiality test:

- at least 50 comparable pairs across at least 5 days;
- no single day contributing more than 40% of pairs;
- at least 60% of daily averages pointing in the same direction;
- a median paired delta with the same sign as the mean effect.

## Validation

Continue the unchanged Stage-2 runtime and use the authority scorecard as an
observation surface. A future authority reduction is allowed only when the
paired effect and promotion stability contracts both pass. Entry tightening and
no-trade still require explicit adoption/control evidence.
