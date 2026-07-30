# Q18 Validation Audit - 2026-07-30

## Verdict

The Q18 decision is confirmed:

`RETAIN SHADOW`

This audit independently recalculated the source populations, attempted
episode-level forward reconstruction with the production forward calculator,
regenerated the cumulative report, and ran the relevant regression tests.

## Persisted-Label Population

The frozen Q18 target is the subtype v2 value persisted at observation time:

`confirmed_post_reclaim_pullback`

| Measure | Verified result |
| --- | ---: |
| Loaded shadow payloads | 20,820 |
| Raw persisted-label rows | 80 |
| Canonically deduplicated rows | 36 |
| Independent 15-minute episodes | 35 |
| Episode days | 21 |
| Distinct symbols | 18 |
| Largest day share | 11.43% |
| Largest symbol share | 22.86% |
| Persisted episode forward outcomes | 0 |

Applying the current classifier retrospectively produces 84 raw rows, 40
deduplicated rows, and 39 episodes. Those four additional rows are excluded
because Q18 is frozen to the label persisted at observation time. Reclassifying
historical rows with current code would introduce schema drift into the review.

## Retrospective Episode Reconstruction

The production `attach_forward_outcomes` calculator was applied to the original
candidate snapshot series. It could reconstruct only part of the 35 episodes.

The live-net basis subtracts the fixed 0.28% real-account cost and slippage
assumption.

| Horizon | Observed | Coverage | Live-net average | Profit factor | MDD |
| --- | ---: | ---: | ---: | ---: | ---: |
| +5m | 11 | 31.43% | -0.0986% | 0.6309 | -2.0572% |
| +15m | 15 | 42.86% | -0.1595% | 0.6527 | -4.5598% |
| +30m | 11 | 31.43% | +0.4158% | 3.1106 | -1.0392% |
| +60m | 14 | 40.00% | -0.3398% | 0.5568 | -7.6723% |

The fixed Q18 coverage requirement is at least 90%. No horizon reaches 43%.
The positive +30m result is therefore promising but not promotion-grade.
The negative +5m, +15m, and +60m results also show that the available evidence
does not support a broad hold or entry policy.

## Daily Aggregate Cross-Check

The daily summaries retain a different, aggregate population:

| Measure | Verified result |
| --- | ---: |
| Candidate observations | 27 |
| Forward-observed observations | 26 |
| Days | 14 |
| Generic observation coverage | 96.30% |
| +30m observations contributing to the weighted mean | 25 |
| Weighted +30m live-net expectancy | +0.2447% |

The 13 days with a +30m daily value produce:

| Measure | Verified result |
| --- | ---: |
| Positive days | 8 |
| Positive-day ratio | 61.54% |
| Unweighted day-average live net | +0.3276% |
| Day-level proxy profit factor | 2.0557 |
| Day-level proxy MDD | -3.0441% |

These values exactly match the Q18 close report. They remain proxies and cannot
replace the required episode-level population.

## Scanner Baseline Cross-Check

On the same 13 calendar days used by the daily +30m proxy:

| Measure | Verified result |
| --- | ---: |
| Scanner Rank 1 observed episodes | 123 |
| +30m live-net expectancy | -0.3521% |
| Profit factor | 0.4453 |
| Win rate | 30.89% |

The post-reclaim aggregate is better than this Scanner baseline, but the two
populations have different observation coverage and cannot authorize
production promotion.

## Strategist Cross-Check

The independent paired-day recalculation reproduced the cumulative report:

| Horizon | Days | Strategist better | Strategist worse | B minus A |
| --- | ---: | ---: | ---: | ---: |
| +5m | 26 | 12 | 13 | -0.0026% |
| +15m | 26 | 12 | 13 | -0.0588% |
| +30m | 26 | 13 | 12 | -0.0285% |
| EOD | 22 | 9 | 13 | -0.2602% |

This does not demonstrate Strategist ranking alpha. It also does not justify
removing Strategist weighting because the raw Scanner baseline is
cost-negative.

## Reproducibility Checks

- The official cumulative generator completed successfully for
  `2026-06-01` through `2026-07-30`.
- Regeneration produced no tracked-file difference.
- Relevant tests: `23 passed`.
- Git worktree: clean.
- Local `HEAD` equals `origin/main`.

## Final Decision Logic

`PROMOTE` is rejected because episode forward coverage is far below 90%, the
persisted artifacts contain no episode outcome, and three of four reconstructed
horizons are cost-negative.

`REJECT` is also too strong because both the retained daily aggregate and the
limited reconstructed +30m sample are positive and outperform same-window
Scanner Rank 1.

The evidence-driven result remains:

`RETAIN SHADOW`

No five-day extension and no Q19 are authorized.
