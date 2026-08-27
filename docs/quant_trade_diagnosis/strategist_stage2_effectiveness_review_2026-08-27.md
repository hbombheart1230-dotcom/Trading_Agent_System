# Strategist Stage-2 Effectiveness Review

Date: 2026-08-27

Status: EVALUATION ONLY

This review does not change Strategist, Scanner, Commander, Monitor, or order
execution behavior.

## Question

The review separates three different questions that were previously hidden
under the ambiguous label `Rank-1`:

1. Does the first Scanner Top-1 under the Stage-1 strategy frame have absolute
   forward edge?
2. Does the post-Scanner Stage-2 refresh improve that candidate?
3. Are there observable conditions that separate useful refreshes from harmful
   refreshes?

Definitions:

- `R1`: first Scanner Top-1 after Stage-1 and before Stage-2 refresh.
- `R2`: Scanner Top-1 after Stage-2 tactical refresh and Scanner rerun.
- Stage-2 target: the symbol explicitly reviewed by the Stage-2 LLM.

## Evidence Coverage

| Evidence | Count |
|---|---:|
| Refresh records with R1/R2 roles | 6,048 |
| Directly linked Stage-2 responses | 1,407 |
| R1=R2 windows | 402 |
| R1!=R2 windows | 1,005 |
| Independent Stage-2 episodes, 30-minute cooldown | 683 |
| Independent changed-symbol episodes | 582 |
| Independent changed-symbol episodes with +30m pair | 75 across 7 days |

An independent episode keeps the first decision for a day and R1 symbol, then
applies a 30-minute cooldown. This prevents overlapping forward windows from
being treated as independent samples.

## Stage-1 R1 Absolute Outcome

These are independent 30-minute episodes across all refresh windows. Net
returns subtract the fixed 0.28% live-account round-trip cost.

| Horizon | N / Days | Gross Avg / Median | Net Avg / Median | Net Win | Net PF |
|---|---:|---:|---:|---:|---:|
| +5m | 199 / 12 | +0.6932% / 0.0000% | +0.4132% / -0.2800% | 24.62% | 1.7835 |
| +15m | 187 / 11 | +0.6415% / 0.0000% | +0.3615% / -0.2800% | 33.16% | 1.5219 |
| +30m | 180 / 12 | +0.6302% / +0.0377% | +0.3502% / -0.2424% | 37.78% | 1.4374 |
| +60m | 155 / 12 | +0.1218% / -0.0374% | -0.1582% / -0.3174% | 40.00% | 0.8426 |
| EOD | 69 / 9 | +1.2268% / +0.2116% | +0.9468% / -0.0684% | 42.03% | 2.6394 |

Interpretation:

- R1 is not a high-win-rate signal.
- Its positive average is produced by a small right tail of large winners.
- +60m is the weakest observed horizon.
- EOD has a strong average and profit factor, but a negative net median and
  only 9 days of evidence. It does not authorize indiscriminate holding.

### Sensitivity

| Variant | Horizon | N | Net Avg / Median | Net Win | Net PF |
|---|---|---:|---:|---:|---:|
| Exclude `top_change_rate` source | +30m | 148 | -0.1895% / -0.2800% | 35.14% | 0.7415 |
| Exclude `top_change_rate` source | EOD | 66 | +0.1428% / -0.1426% | 39.39% | 1.2365 |
| Exclude absolute gross return >=15% | +30m | 178 | +0.0577% / -0.2705% | 37.08% | 1.0713 |
| Exclude absolute gross return >=15% | EOD | 68 | +0.5236% / -0.0909% | 41.18% | 1.8936 |

The broad R1 intraday edge is not robust. The strongest contribution comes
from a small number of `top_change_rate` and extreme-return candidates.

## R1 Versus R2

### Directly Linked Raw Windows

| Horizon | N / Days | R1 Avg | R2 Avg | R2-R1 Avg / Median |
|---|---:|---:|---:|---:|
| +5m | 162 / 10 | +0.8567% | -0.0154% | -0.8720% / +0.0315% |
| +15m | 145 / 9 | +0.8320% | +0.0845% | -0.7475% / -0.1743% |
| +30m | 124 / 8 | +0.6910% | -0.0050% | -0.6960% / -0.2135% |
| +60m | 100 / 7 | +0.5698% | +0.1595% | -0.4103% / -0.0941% |
| EOD | 43 / 3 | +2.3239% | +2.0677% | -0.2562% / +0.7684% |

### Independent Changed-Symbol Episodes

| Horizon | N / Days | R1 Avg / Win | R2 Avg / Win | R2-R1 Avg / Median |
|---|---:|---:|---:|---:|
| +5m | 98 / 9 | +1.0062% / 40.82% | +0.0254% / 44.90% | -0.9808% / +0.0163% |
| +15m | 92 / 8 | +0.7508% / 47.83% | +0.0745% / 46.74% | -0.6763% / -0.1345% |
| +30m | 75 / 7 | +0.9126% / 52.00% | +0.1235% / 40.00% | -0.7891% / -0.0934% |
| +60m | 59 / 6 | +0.7983% / 45.76% | +0.1749% / 55.93% | -0.6234% / -0.2533% |
| EOD | 27 / 3 | +2.4580% / 59.26% | +1.2783% / 70.37% | -1.1797% / +0.6654% |

The R1 average is higher, but the conclusion is not directionally stable. In
the raw daily averages R2 beat R1 on five of eight days; a small number of
large R1 winners caused the negative aggregate delta. The largest independent
day still contributes 49.33% of +30m pairs.

## Critical Semantic Finding

Stage-2 did not explicitly choose the replacement symbol:

- In all 124 comparable changed-symbol +30m windows, Stage-2 `target_symbol`
  matched R1.
- Across all changed-symbol records, 994 had a Stage-2 target matching R1 and
  11 had no target. No observed changed-symbol record explicitly targeted R2.
- The runtime calls `strategist_node` again for Stage-2, recomputes a broad
  deterministic strategy frame, waits for the LLM response, and reruns Scanner.
- R2 is therefore a combined effect of elapsed time, refreshed market data,
  deterministic frame reconstruction, Stage-2 tactical fields, and Scanner
  reranking.

Consequently, `R1 -> R2` is not a clean estimate of Stage-2 LLM candidate
selection alpha. It is the post-refresh pipeline effect.

There is also a target-consistency risk: Stage-2 monitor and entry guidance is
written for R1, while the final selected candidate can become R2. Applying
target-specific guidance to a different symbol would be a semantic mismatch.

## Exploratory Separators

All rows below use independent changed-symbol +30m episodes.

| Separator | N / Days | R1 Avg | R2 Avg | R2-R1 | Interpretation |
|---|---:|---:|---:|---:|---|
| R1 score margin <=0.05 | 39 / 5 | -0.3040% | -0.0319% | +0.2721% | weak R1; rerun avoids some loss but creates no clear absolute edge |
| R1 score margin 0.05-0.15 | 22 / 5 | +1.0296% | +0.6114% | -0.4182% | preserve-R1 candidate, still concentrated |
| R1 score margin 0.15-0.30 | 12 / 3 | +2.2844% | -0.3279% | -2.6123% | strong preserve-R1 signal, insufficient days |
| R1 volume surge absent | 44 / 6 | +1.4551% | -0.0746% | -1.5298% | R1 large-winner tail; max day 43.18% |
| R1 volume surge positive | 31 / 5 | +0.1426% | +0.4048% | +0.2623% | possible rerun-friendly branch; max day 61.29% |
| sector-theme-only source | 37 / 5 | -0.1426% | +0.3382% | +0.4809% | most plausible R2-friendly source branch |
| liquidity-activity source | 31 / 3 | +0.5051% | -0.1520% | -0.6571% | R1 preservation candidate |
| contains top-change source | 5 / 3 | +12.7611% | -0.1123% | -12.8734% | major tail driver, far too small for policy |
| opening 0-20m | 10 / 4 | +3.3519% | +1.3489% | -2.0030% | refresh can lose fast opening leaders |
| opening 20-60m | 6 / 2 | +2.7686% | -0.5891% | -3.3577% | same signal, insufficient sample |

Most useful current discriminator hypothesis:

```text
Transient activity leader
  = top-change / top-value / top-volume source
  + meaningful R1 score margin
  + opening or fast-moving context

Such a candidate may lose rank during Stage-2 latency even though the original
R1 retains the stronger forward tail.
```

The opposite tentative branch is sector-theme-only with a very small R1 score
margin, where the fresh Scanner rerun may be more useful.

Neither branch passes promotion stability yet.

## Stage-2 Recommendation Utility

| Stage-2 surface | Current conclusion |
|---|---|
| Explicit candidate selection | Not observed; Stage-2 normally targets R1 |
| Post-refresh Scanner rerank | Measurable as a pipeline effect, not pure LLM alpha |
| Entry tightening | Not measurable without an adoption trace and untreated control |
| No-trade recommendation | Not measurable separately from Commander/Monitor veto |
| `avoid_rank1` | Positive R2-R1 delta in 4 independent pairs across 3 days; insufficient |
| `watch_rank1_with_tighter_gates` | Negative average delta, but mixes candidate rerun and target-specific policy |
| Memory caution | Confounded by weak/volatile symbol selection; no causal conclusion |

## Decision

1. Do not disable or reduce Stage-2 based on the current aggregate.
2. Do not describe R2 candidate changes as explicit Stage-2 selections.
3. Treat Stage-2 target consistency as the first correctness question.
4. Preserve separate R1 and R2 forward evidence in every daily report.
5. If a behavior patch is later considered, test exactly one rule:
   target-specific Stage-2 guidance may only govern its `target_symbol`; a new
   R2 symbol must be treated as a fresh Scanner candidate rather than inheriting
   R1 guidance.
6. Candidate preservation by source family or score margin remains shadow-only
   until the same direction appears across distributed days.

## Artifacts

- `reports/evaluation/agent_effectiveness/cumulative_20260601_20260827/strategist_stage2_effectiveness_deep_dive.json`
- `reports/evaluation/agent_effectiveness/cumulative_20260601_20260827/strategist_stage2_effectiveness_deep_dive.md`
- `reports/evaluation/agent_effectiveness/cumulative_20260601_20260827/strategist_stage2_authority_review.json`
- `reports/evaluation/agent_effectiveness/cumulative_20260601_20260827/strategist_stage2_authority_review.md`

