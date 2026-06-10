# Q8 Below-VWAP Reclaim Subtype Review: 2026-05-18 to 2026-06-08

Purpose: decide whether `below_vwap_reclaim_not_ready` can be relaxed by
subtype.

This review is evaluation-only. It does not change entry logic, exit logic,
scanner ranking, monitor guards, Strategist prompts, or broker execution.

## Source

- Historical review:
  `docs/tactics/q8_historical_review_2026-05-18_to_2026-06-08.md`
- JSON artifact:
  `reports/dev/analysis/q8_historical_review/q8_historical_review_2026-05-18_to_2026-06-08.json`

## Data Boundary

Subtype counts are available across the recent Q8 shadow period.

Subtype forward outcomes are available only after entry-lane observation fields
were added to daily summaries. In this review, subtype forward evidence covers
2 forward days.

This means subtype evidence is useful for direction, but not yet enough for a
live behavior promotion.

## Subtype Counts

| Subtype | Count |
| --- | ---: |
| `true_below_vwap_failure` | 595 |
| `near_vwap_reclaim_setup` | 70 |
| `reclaim_in_progress_with_improving_volume` | 42 |
| `post_reclaim_pullback_candidate` | 1 |

## Classifier V2 Counts

`below_vwap_reclaim_classifier_v2` keeps the old subtype for compatibility and
adds `subtype_v2` for more diagnostic review.

| Subtype V2 | Count |
| --- | ---: |
| `deep_below_vwap_failure` | 2,004 |
| `ordinary_below_vwap_failure` | 1,339 |
| `shallow_below_vwap_rebound` | 741 |
| `near_vwap_reclaim_setup` | 211 |
| `index_or_largecap_rebound_below_vwap` | 95 |
| `confirmed_post_reclaim_pullback` | 12 |

## Subtype Forward Outcomes

| Subtype | n | obs | +3m | +5m | +15m | +30m | +60m | MFE5 | MAE5 | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `true_below_vwap_failure` | 590 | 535 | +0.0444% | +0.1031% | +0.3762% | +0.7208% | +1.4628% | +0.5336% | -0.3782% | `review_classifier_or_label` |
| `near_vwap_reclaim_setup` | 70 | 67 | -0.0167% | +0.0218% | -0.2083% | -0.4298% | -0.0821% | +0.3981% | -0.3962% | `retain_under_observation` |
| `reclaim_in_progress_with_improving_volume` | 42 | 37 | +0.0254% | -0.0704% | -0.1925% | -0.2157% | +0.1667% | +0.3438% | -0.3275% | `keep_blocked` |

## Interpretation

The result is not what the label names imply.

`true_below_vwap_failure` is currently the strongest subtype by forward
outcome. It has positive average returns from +3m through +60m. That does not
mean the system should buy true failures. It means the subtype label or
classifier boundary is likely too crude.

`near_vwap_reclaim_setup` looks intuitive as a relaxation candidate, but the
forward result is weak after +5m and negative at +15m, +30m, and +60m.

`reclaim_in_progress_with_improving_volume` is not ready for promotion. +5m and
+15m are negative, and +60m turns only mildly positive.

## Decision

Do not relax `below_vwap_reclaim_not_ready` globally.

Do not promote `near_vwap_reclaim_setup` or
`reclaim_in_progress_with_improving_volume` to live entry behavior yet.

Before behavior promotion, use the repaired subtype taxonomy:

- check whether `deep_below_vwap_failure` and `ordinary_below_vwap_failure`
  remain negative after forward evidence is collected under v2
- test whether `shallow_below_vwap_rebound` or
  `index_or_largecap_rebound_below_vwap` explains the old positive
  `true_below_vwap_failure` result
- separate large-cap/index rebound behavior from ordinary weak below-VWAP
  failures using `index_or_largecap_rebound_below_vwap`
- keep `near_vwap_reclaim_setup` observation-only until it shows positive +15m
  or +30m evidence

## Next Action

The classifier refinement is now patched as observation-only:

`below_vwap_reclaim_classifier_v2`

Next live sessions should collect forward outcomes by `subtype_v2`.

Promotion rule remains:

No subtype becomes live behavior until it shows stable forward advantage and
acceptable adverse movement after the classifier is repaired.
