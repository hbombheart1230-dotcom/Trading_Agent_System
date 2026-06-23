# Q8 Evaluation Contract

Last updated: 2026-06-16

This document is the canonical contract for Q8 evaluation and promotion review.
It is intentionally stricter than older Q8 daily reviews.

## Scope

This contract applies to:

- quant shadow candidate evaluation
- Q8 blocker review
- Q8 lane decision table
- Q8 historical review
- Q8 trusted reaggregation
- promotion framework decisions that use Q8 evidence

It does not change trading behavior by itself.

## Canonical Candidate Unit

Q8 must deduplicate candidates before forward performance is averaged.

Canonical dedupe key:

```text
day + symbol + baseline_epoch + entry_lane_subtype
```

Do not use raw candidate count as promotion evidence.
Do not use role, reason, rank, or tactic ID as the dedupe key for Q8 promotion
review.

## Trusted Forward Outcome

A forward checkpoint is trusted only when:

- the observed row is from the same KST trading day as the baseline
- the observed row is within 180 seconds of the target checkpoint
- the checkpoint status is `observed`

The following checkpoint statuses are not performance evidence:

- `pending`
- `stale_cross_day_observation`
- `stale_forward_gap`

## Trust Gate

Q8 promotion review is blocked unless all conditions below pass:

| Requirement | Minimum |
| --- | ---: |
| Trusted deduped forward observations | 100 |
| Trusted forward coverage | 70% |
| Duplicate rate | <= 75% |
| Repeatable promotion-watch candidate | required |

A repeatable promotion-watch candidate must have:

| Requirement | Minimum |
| --- | ---: |
| Trusted observations | 50 |
| Observed trading days | 2 |
| Average +5m return | > 0 |
| Average +15m return | > 0 |

If the trust gate fails, all Q8 conclusions are observation-only.
Blocker reviews and lane tables may show diagnostic signals, but they must not
recommend a behavior patch.

## Decision Authority

Allowed statuses:

- `promotion_review_ready`: Q8 evidence may be reviewed for promotion.
- `promotion_blocked_sample_or_coverage`: trusted sample or coverage is not
  sufficient.
- `promotion_blocked_no_repeatable_candidate`: no candidate repeated across
  enough days with positive forward evidence.

Allowed actions:

- `PROMOTE`: only after trust gate passes and Promotion Framework review is
  complete.
- `RETAIN UNDER OBSERVATION`: default when trust gate fails.
- `ADJUST AND RE-TEST`: allowed only after trust gate passes.
- `REJECT`: allowed when trusted evidence is consistently negative.
- `DEPRECATE`: allowed for already-official policy with trusted negative
  evidence.

## Legacy Evidence Rule

Q8 daily or historical documents generated before this contract are legacy
observation material unless regenerated with:

- canonical dedupe key
- trusted same-day forward filtering
- evaluation trust gate

Legacy documents may explain why a question was raised. They must not be used
as standalone promotion evidence.

## Change Control

Changing any value in this contract requires:

- explicit operator approval
- a matching code change in `libs/reporting/q8_evaluation_contract.py`
- an update to this document
- focused regression tests

No single report, day, or intuitive market observation changes this contract by
itself.
