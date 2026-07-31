# Existing Evidence Mining Result

## Decision

The June-July evidence does not support another immediate live trading patch.

One bounded discovery candidate remains:

`OPEN_0_20_RANK1_30M`

This means:

- Scanner rank 1
- decision during the first 20 minutes
- next-minute reference entry
- fixed +30 minute outcome
- 0.28% round-trip cost applied

The candidate is `FUTURE_CONFIRMATION_REQUIRED`. It is not promoted and does
not change Scanner, Strategist, Commander, Monitor, entry, exit, or execution
behavior.

The first generated result incorrectly used the open of the candle containing
the decision timestamp. That price was not tradable after the decision. The
shared offline entry helper now uses the first candle timestamp strictly after
the decision, and every number below was regenerated through 2026-07-30.
The 2026-07-31 implementation day is excluded.

A second, weaker cohort is retained only as insufficient evidence:

`BREAKOUT_VWAP_HOLD_VOLUME_CONFIRMED`

It has fewer than 25 observed +30 minute paths and cannot justify relaxing a
guard.

## Evidence Inventory

| Evidence | Count |
| --- | ---: |
| Raw Q9 Scanner windows | 13,174 |
| Canonical valid windows | 12,622 |
| Trading days | 28 |
| Point-in-time Scanner symbols | 327 |
| Total symbols requiring minute history | 387 |
| Complete minute-history symbols | 233 |
| Reconstructed Scanner episodes | 5,292 |
| Quant-shadow source files | 20,863 |
| Deterministic 15-minute snapshots read | 1,131 |
| Quant-shadow 15-minute episodes | 1,937 |
| Realized trade evaluations | 105 |

The complete machine-readable output is:

`reports/evaluation/offline_alpha/existing_evidence_mining/2026-06-01_2026-07-30/existing_evidence_mining.json`

## Main Findings

### 1. The captured candidate universe has no broad edge

At +30 minutes after 0.28% cost:

| Rank | Observed | Win Rate | Average Net | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| Rank 1 | 896 | 35.7% | -0.2774% | 0.6562 |
| Rank 2-3 | 1,456 | 35.0% | -0.3637% | 0.5444 |
| Rank 4-5 | 1,135 | 30.1% | -0.3082% | 0.5713 |
| Rank 6-10 | 1,051 | 35.6% | -0.2958% | 0.6147 |

Selecting rank 1 is better than selecting lower ranks, but rank 1 is still
negative when all decision times are combined.

### 2. Time of day is the strongest retained separation

At +30 minutes after cost:

| Decision Time | Observed | Win Rate | Average Net | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| 09:00-09:20 | 378 | 51.1% | +0.3882% | 1.3615 |
| 09:20-10:00 | 571 | 39.1% | -0.3933% | 0.6102 |
| 10:00-12:00 | 1,532 | 29.8% | -0.5018% | 0.3822 |
| 12:00-14:00 | 1,404 | 33.1% | -0.2947% | 0.5238 |
| 14:00-close | 653 | 31.9% | -0.2734% | 0.5678 |

The broad historical system selected candidates throughout the day, but only
the first 20 minutes showed positive aggregate expectancy.

### 3. Opening rank 1 is a discovery candidate, not proof

| Split | Observed | Win Rate | Average Net | Profit Factor | Positive Days |
| --- | ---: | ---: | ---: | ---: | ---: |
| Overall | 65 | 61.5% | +0.7502% | 1.7727 | 62.5% |
| Calibration through 07-10 | 25 | 64.0% | +1.0330% | 2.7504 | 63.6% |
| Retrospective from 07-13 | 40 | 60.0% | +0.5735% | 1.4744 | 61.5% |

The retrospective trade metrics remain positive, but the result was discovered
after outcome inspection. It passes the retrospective screening gates after
the conservative entry correction, but cannot be treated as an untouched
holdout. EOD performance is negative, so this is specifically a short
intraday path candidate.

### 4. Tight fixed exits destroy the opening signal

Opening rank 1 path simulation:

| Target / Stop / Time | Count | Average Net | Profit Factor |
| --- | ---: | ---: | ---: |
| 1.0% / 0.5% / 30m | 69 | -0.2821% | 0.4365 |
| 1.5% / 0.75% / 30m | 69 | -0.2140% | 0.6490 |
| 2.0% / 1.0% / 30m | 69 | -0.0226% | 0.9650 |
| Fixed +30m observation | 65 | +0.7502% | 1.7727 |

The evidence does not support another tighter stop/target patch. Same-bar
target/stop collisions were conservatively scored as stop first.

### 5. Most blocked opportunities were correctly rejected

Representative +30 minute net outcomes:

| Blocker | Observed | Average Net | Profit Factor |
| --- | ---: | ---: | ---: |
| below_vwap_reclaim_not_ready | 434 | -1.0998% | 0.2486 |
| breakout_not_ready | 168 | -0.8489% | 0.3304 |
| pullback_not_mature | 129 | -0.2717% | 0.5034 |
| volume_confirmation_missing | 100 | -0.4322% | 0.6139 |
| volume_insufficient | 96 | -0.8126% | 0.3335 |
| human_chart_sanity_guard_blocked | 45 | -1.1939% | 0.2280 |
| cost_edge_fail | 41 | -0.4022% | 0.4239 |

This rejects a broad guard-relaxation response. The observed losses were not
mainly caused by blocking these cohorts.

The exception under observation is
`breakout_above_recent_high_with_vwap_hold_and_volume_confirmation`: 18
observed +30 minute paths, +1.6170% average net, and 2.8458 profit factor.
Its sample is too small and already inspected.

### 6. Holding longer is not the general repair

| Actual Trade Group | Count | Average Return | Profit Factor |
| --- | ---: | ---: | ---: |
| All realized | 105 | -0.8683% | 0.2831 |
| Exit before minimum hold | 30 | -0.6746% | 0.2523 |
| Minimum-hold compliant | 75 | -0.9458% | 0.2914 |

Minimum-hold-compliant trades performed worse than early exits. Horizon
compliance remains an integrity requirement, but it is not supported as the
primary alpha repair.

## Integrity Limits

- July outcomes were already inspected. This is retrospective discovery, not
  untouched validation.
- 78.3% of historical candidate rows have no retained source, so source-level
  attribution is weak.
- Only 4.8% of windows contain a retained market-native candidate.
- 19.6% of valid windows are sector-theme-only.
- Q9 pre-Strategist ranking is a control inside the captured candidate
  universe, not a full-market control.
- The corrected current Scanner universe differs from parts of the historical
  universe.
- Complete cached minute history exists for 233 of 387 requested symbols.
  Horizon metrics report observed coverage and do not impute missing prices.

## Closed Interpretations

The existing evidence does not support:

- promoting any H1-H9 offline hypothesis
- relaxing all entry guards
- blaming Strategist or Commander for broad candidate underperformance
- treating rank 1 alone as a profitable all-day policy
- fixing performance by extending every hold
- fixing performance with tight fixed targets and stops
- opening another unconstrained hypothesis search

## Next Action

Do not request another broad historical mining pass and do not create a new Q
phase from this result.

Keep exactly one primary candidate frozen:

`OPEN_0_20_RANK1_30M`

Future evidence must come from the corrected Scanner universe and must be
recorded prospectively without threshold changes. The secondary breakout
cohort may be reported, but it cannot trigger behavior changes until it reaches
the predeclared evidence threshold.

All other runtime behavior remains unchanged.
