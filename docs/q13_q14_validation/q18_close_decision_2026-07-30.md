# Q18 Close Decision - 2026-07-30

## Decision

`RETAIN SHADOW`

Q18 is closed immediately from existing evidence. Do not start the optional
five-day extension.

The confirmed post-reclaim-pullback subtype remains promising, but the
canonical artifacts do not retain episode-level forward outcomes required for
promotion. Waiting five more days without changing that artifact contract
would not repair the historical evidence gap.

## Independent Episode Reconstruction

Source:

- clean `data/logs/quant_shadow_candidates`
- 2026-06-01 through 2026-07-30
- subtype v2: `confirmed_post_reclaim_pullback`
- 15-minute same-day/same-symbol episode gap
- first qualifying observation as episode reference

| Measure | Result |
| --- | ---: |
| Raw subtype rows | 80 |
| Canonically deduplicated rows | 36 |
| Independent episodes | 35 |
| Episode days | 21 |
| Distinct symbols | 18 |
| Largest single-day share | 11.43% |
| Largest single-symbol share | 22.86% |
| Episode rows with persisted forward outcome | 0 |

The candidate passes count and concentration structure gates. It fails the
artifact-integrity gate because episode returns cannot be reconstructed from
the candidate rows.

## Retained Aggregate Evidence

Daily summaries retained a smaller forward-observed population:

- 26 observations
- 14 days
- 96.3% aggregate coverage
- weighted +30m live-net expectancy: +0.2447%

Day-level +30m proxy:

| Measure | Result |
| --- | ---: |
| Days with +30m value | 13 |
| Positive live-net days | 8 |
| Positive-day ratio | 61.54% |
| Unweighted day-average live-net | +0.3276% |
| Day-level proxy profit factor | 2.0557 |
| Day-level proxy MDD | -3.0441% |

Same-window Scanner Rank 1:

| Measure | Result |
| --- | ---: |
| Observed episodes | 123 |
| +30m live-net expectancy | -0.3521% |
| +30m profit factor | 0.4453 |
| Win rate | 30.89% |

The subtype is materially more promising than same-window Scanner Rank 1.
However, daily aggregate statistics cannot substitute for the episode-level
profit factor and drawdown required by the fixed Q18 contract.

## Why This Is Not PROMOTE

- The 35 reconstructed episodes have no persisted per-episode forward result.
- The 26 aggregate observations cannot be reliably joined back to the 35
  episodes.
- Episode win rate, average loss, profit factor, MDD, and outcome concentration
  are therefore unavailable.
- Reconstructing or distributing daily averages across episodes would invent
  evidence.

## Why This Is Not REJECT

- +15m and +30m aggregate live-net expectancy are positive.
- Positive performance spans multiple days and symbols.
- Day and symbol concentration are below the fixed limits.
- The day-level proxy outperforms same-window Scanner Rank 1.

The correct fixed-contract outcome is `RETAIN SHADOW`.

## Strategist Ranking Decision

The paired 26-day comparison remains:

| Horizon | Strategist B minus Scanner A |
| --- | ---: |
| +5m | -0.0026% |
| +15m | -0.0588% |
| +30m | -0.0285% |
| EOD | -0.2602% |

Strategist-guided ranking has not demonstrated alpha. Raw Scanner Rank 1 is
also cost-negative, so removing Strategist weighting would replace one
unprofitable ranking with another rather than establish edge.

Decision:

`NO_STRATEGIST_RANKING_BEHAVIOR_PATCH`

Retain Strategist scenario, tactic, horizon, risk, and explanation roles.
Continue recording raw and strategist-guided ranks, but do not tune or disable
the weighting from the present evidence.

## System-Level Conclusion

Q8-Q18 did not establish a production-quality positive trading edge.

What was established:

- artifact and attribution integrity
- defensive value of Q15 runner-up restriction
- defensive value of Q16 directional evidence
- severe damage from same-day same-symbol reentry after a loss
- one promising but non-promotable post-reclaim subtype

What was not established:

- profitable Scanner ranking
- Strategist ranking alpha
- profitable opening, large-cap, or BTC baseline
- production-ready Monitor entry subtype
- repaired horizon policy profitability

No additional live evaluation phase is authorized from this result.

## Next Direction

Keep the current live system defensive and low-frequency. Runtime artifacts may
continue accumulating, but they are no longer an active numbered evaluation
program.

The next development direction is offline alpha research with explicit,
testable strategy hypotheses and historical minute data. A candidate must
demonstrate positive cost-adjusted expectancy before it is connected to the
multi-agent runtime.

Do not create Q19 from this decision.
