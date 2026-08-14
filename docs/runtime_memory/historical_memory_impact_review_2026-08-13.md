# Historical Memory Impact Review - 2026-08-13

## Scope

- Period: 2026-06-01 through 2026-08-13
- Population: actual `selected_symbol_tactical_review` Stage-2 calls
- Stage-2 source: `data/evidence_ledger/events.jsonl`
- Memory source: same-run canonical Strategist artifact
- Q9 decision source: same-run Q9 decision window
- Behavior change: none

Generated artifacts:

- `reports/evaluation/range/2026-06-01_2026-08-13/memory_contamination_review.json`
- `reports/evaluation/range/2026-06-01_2026-08-13/memory_contamination_review.md`

## Strict Classification

| Cohort | Stage-2 calls | Share | Q9-linked | Tightened |
| --- | ---: | ---: | ---: | ---: |
| MEMORY_CLEAN | 2,218 | 85.57% | 1,794 | 1,831 |
| SYMBOL_MEMORY_MISMATCH | 374 | 14.43% | 291 | 304 |
| STALE_OR_CONTRADICTORY_MEMORY | 0 | 0.00% | 0 | 0 |
| INSUFFICIENT_MEMORY_EVIDENCE | 0 | 0.00% | 0 | 0 |

The Q9-linked mismatch rate is 291 / 2,085 = 13.96%.

## Monthly Distribution

| Month | Stage-2 | Q9-linked | Clean | Mismatch | Mismatch tightened |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-06 | 649 | 158 | 529 | 120 | 110 |
| 2026-07 | 1,164 | 1,160 | 1,060 | 104 | 91 |
| 2026-08 | 779 | 767 | 629 | 150 | 103 |

## What Changed In Interpretation

### Preserve

The following evidence does not use selected-symbol memory as its price or rank authority and remains valid:

- Scanner P/A raw ranking observations
- raw Rank-1 candidate identity and score components
- minute-candle forward returns
- opening shooting analysis
- horizon backfills
- latent reactivation analysis
- canonical Rank-1 feature mart

### Recompute or Filter

The following claims must use `MEMORY_CLEAN` rows when estimating agent quality:

- Strategist B degradation or improvement
- Commander C over-filtering or alpha
- Stage-2 rejection and tightening effectiveness
- Q14 Strategist Override attribution
- promotion/deprecation decisions based on B/C deltas

The unfiltered historical output remains valid as a record of actual runtime behavior. It is not valid as a pure measurement of Strategist or Commander ability.

## Q9 Forward Reclassification

Direct linkage recovered 2,079 Q9 decision windows: 1,788 clean and 291 cross-symbol mismatch. Six of the 2,085 Q9-linked Stage-2 calls had no directly named shadow payload and were not forced into the comparison.

The table uses same-window comparisons. `B-A` is Strategist-ranked return minus Scanner control return. `C-B` compares Commander policy net return with Strategist B net return. C no-trade is valued at 0%.

| Cohort | Horizon | A/B pairs | B gross avg | B-A avg | C comparisons | C policy net avg | C-B avg |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MEMORY_CLEAN | +5m | 1,028 | -0.1800% | +0.0966%p | 1,083 | -0.4502% | +0.7698%p |
| MEMORY_CLEAN | +15m | 1,049 | -0.1891% | -0.0071%p | 1,086 | -0.4794% | +0.7505%p |
| MEMORY_CLEAN | +30m | 1,018 | -0.1702% | +0.0535%p | 1,066 | -0.4719% | +0.7395%p |
| MEMORY_CLEAN | +60m | 934 | -0.4117% | -0.0112%p | 962 | -0.5901% | +0.8620%p |
| MEMORY_CLEAN | EOD | 1,184 | -0.6306% | +0.0953%p | 1,210 | -0.9050% | +0.7676%p |
| SYMBOL_MEMORY_MISMATCH | +5m | 156 | -0.5293% | -0.1701%p | 163 | -0.3746% | +1.1915%p |
| SYMBOL_MEMORY_MISMATCH | +15m | 154 | -0.4898% | -0.2481%p | 161 | -0.3713% | +1.1553%p |
| SYMBOL_MEMORY_MISMATCH | +30m | 153 | -0.5408% | -0.2608%p | 162 | -0.3489% | +1.2287%p |
| SYMBOL_MEMORY_MISMATCH | +60m | 130 | -0.6131% | -0.4452%p | 137 | -0.1486% | +1.5013%p |
| SYMBOL_MEMORY_MISMATCH | EOD | 182 | +0.1966% | +0.1761%p | 188 | -0.2497% | +0.5906%p |

Interpretation:

- Clean B-A is small and changes sign by horizon. The historical data does not show stable Strategist ranking alpha.
- Mismatch B-A is negative from +5 through +60 minutes. Cross-symbol memory contamination is therefore consistent with degraded short-horizon ranking, although it is not sole causal proof.
- EOD mismatch behaves differently and does not justify a blanket claim that every contaminated call was harmful.
- C-B is strongly positive because many C decisions avoided B trades whose net return was negative after cost. This uses the active `kiwoom.ka10170` profile at 1.036849%, so it measures loss/cost avoidance, not pure Commander candidate-selection alpha.
- These are shadow forward outcomes. Realized broker PnL remains outside the strict causal linkage boundary below.

## Important Negative Result

Cross-symbol memory did not explain all conservative behavior.

- Mismatch tightening rate: 304 / 374 = 81.28%
- Clean tightening rate: 1,831 / 2,218 = 82.55%
- Mismatch Q9 veto rate: 199 / 291 = 68.38%
- Clean Q9 veto rate: 973 / 1,794 = 54.24%

Mismatch rows were vetoed more often, but tightening was already widespread in clean rows. Therefore:

- memory contamination was a real defect
- it likely worsened some candidate reviews
- it is not the sole cause of low activity or poor win rate
- Scanner/Monitor/strategy-horizon findings still require their existing evidence

## Realized Trade Boundary

No realized trade passed the strict linkage requirement of:

1. same Stage-2 run ID
2. same Stage-2 target symbol
3. trusted behavior outcome

Several trades reused a Strategist run as a later strategy anchor for another symbol. Those trades are not attributed to the earlier Stage-2 target. Historical realized PnL remains valid, but this review does not claim a causal PnL delta for memory contamination.

## Stale and Contradictory Memory

The strict runtime-visible cohort is zero. Raw daily memory artifacts did contain contradictory best/worst rankings historically, but runtime neutralization prevented those rows from remaining visible as directional Stage-2 evidence in this population.

Stale legacy Reporter feedback is excluded from this cohort because its runtime contract already marked it excluded from performance inference.

## Final Decision

1. Do not restart Q8/Q9 validation.
2. Preserve Scanner and offline-alpha conclusions.
3. Exclude `SYMBOL_MEMORY_MISMATCH` from clean Strategist/Commander effectiveness estimates.
4. Keep mismatch rows as an operational-defect cohort.
5. Use the corrected runtime from 2026-08-13 onward for prospective clean evidence.
6. Treat clean B-A as inconclusive/near-neutral rather than evidence that Strategist ranking adds stable alpha.
7. Treat historical C-B as cost-sensitive filtering evidence, not standalone Commander alpha.
