# Q8 Final Comprehensive Review

Date: 2026-06-20

Evaluation window:

```text
Primary trusted window: 2026-06-16 through 2026-06-19
Legacy context window: 2026-05-18 through 2026-06-15
```

This document is the final consolidated Q8 review. It does not change runtime
behavior. Q9 may reuse the findings as evidence, but it must not silently
promote a Q8 observation into policy.

## Executive Conclusion

Q8 succeeded as an observability and rejection framework.

It did not discover a new profitable tactic suitable for promotion.

The strongest conclusions are:

1. Broad VWAP reclaim relaxation should not be promoted.
2. Broad pullback-quality relaxation should not be promoted.
3. Opening momentum relaxation should not be promoted.
4. Runner-up automatic substitution should remain prohibited.
5. Existing volume, chart-sanity, and reclaim confirmation concepts remain
   defensible.
6. The cost-edge concept remains necessary, but its runtime cost profile is
   contaminated by a stale 6.55% conservative floor and must be repaired
   before the gate's strictness can be evaluated accurately.
7. Q8 produced useful conditional signals for Q9, especially by market rail,
   time bucket, and delayed continuation horizon.

Q8 should therefore be closed as:

```text
No new tactic promoted.
Two relaxation candidates rejected.
Existing defensive concepts retained.
Cost-profile implementation defect escalated.
Conditional observations handed to Q9.
```

## Evidence Quality

Final trusted reaggregation:

| Metric | Result | Contract Requirement | Status |
| --- | ---: | ---: | --- |
| Raw candidates | 4,557 | - | context only |
| Deduped candidates | 2,096 | - | canonical sample |
| Duplicate candidates | 2,461 | - | removed |
| Duplicate rate | 54.00% | <= 75% | pass |
| Trusted forward observations | 1,802 | >= 100 | pass |
| Trusted forward coverage | 85.97% | >= 70% | pass |
| Days represented | 4 | candidate-dependent | pass |
| Cumulative trust gate | `promotion_review_ready` | required | pass |
| Would-enter candidates | 9 | - | 0.43% of deduped candidates |

The final counts differ slightly from the June 19 intraday handoff because
closeout added later observations:

```text
Intraday handoff: 4,462 raw / 2,036 deduped / 1,791 trusted
Final reaggregation: 4,557 raw / 2,096 deduped / 1,802 trusted
```

This difference does not change the decisions.

### Important Data Boundaries

- June 19 from approximately 09:00 to 09:30 KST is excluded from opening-lane
  conclusions because the runtime did not start normally.
- Pre-contract historical reports are context only.
- Raw repeated rows are not independent observations.
- Shadow forward returns are gross price movement, not realized broker net PnL.
- Market-rail aggregates are conditional associations, not causal strategy
  effects.

## Candidate Funnel

Raw lane distribution:

| Lane | Raw Count | Raw Share |
| --- | ---: | ---: |
| VWAP reclaim | 2,465 | 54.09% |
| Cost edge | 954 | 20.94% |
| Pullback quality | 408 | 8.95% |
| Volume confirmation | 260 | 5.71% |
| Breakout readiness | 168 | 3.69% |
| Opening momentum | 130 | 2.85% |
| Runner-up selection | 74 | 1.62% |
| Human chart sanity | 48 | 1.05% |
| Confirmed or other | 44 | 0.97% |
| Opening large-cap surge | 6 | 0.13% |

Only 9 of 2,096 deduped candidates reached a would-enter state.

Interpretation:

- Q8 successfully identified where candidates were being blocked.
- The overall gate stack was extremely selective.
- This selectivity cannot be attributed to market quality alone because the
  cost profile was inflated.
- Low would-enter count does not prove that entry rules should be relaxed.
  It proves that gate interactions must be attributed correctly in Q9.

## Primary Lane Results

All percentages below are gross forward price returns from the candidate
baseline.

| Lane | Observed | Days | +5m | +15m | +30m | +60m | MFE5 | MAE5 | Q8 Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| VWAP reclaim | 907 | 4 | -0.0236% | -0.1442% | -0.2863% | -0.3934% | +0.4302% | -0.4673% | keep confirmation |
| Pullback quality | 188 | 4 | -0.0232% | -0.0526% | -0.2831% | -0.6171% | +0.3106% | -0.3376% | reject broad relaxation |
| Opening momentum | 38 | 3 | -0.2502% | -0.2377% | -0.4648% | -0.5002% | +0.8262% | -1.1052% | keep blocked |
| Runner-up selection | 32 | 4 | +0.0365% | -0.0122% | -0.3015% | -0.4159% | +0.2454% | -0.2740% | no automatic substitution |
| Human chart sanity | 26 | 4 | -0.1030% | +0.0322% | -0.0515% | +0.1915% | +0.3377% | -0.4410% | retain guard |
| Breakout readiness | 62 | 4 | -0.0458% | -0.0145% | +0.4302% | +0.7061% | +0.2480% | -0.3207% | delayed-horizon study only |
| Volume confirmation | 83 | 4 | +0.0042% | +0.0071% | +0.8385% | +1.0983% | +0.4352% | -0.6215% | regime/outlier study only |
| Cost edge not met | 445 | 4 | +0.0236% | +0.2085% | +0.2149% | +0.3105% | +0.2918% | -0.3067% | retain concept, repair profile |

### VWAP Reclaim

This was the largest lane and the cleanest negative result.

The lane was negative from +5 minutes through +60 minutes. Adverse excursion
also exceeded favorable excursion.

Useful subtypes:

| Subtype | Observed | +5m | +15m | +30m | +60m | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| ordinary below-VWAP failure | 295 | -0.0084% | -0.0718% | -0.3532% | -0.3395% | keep blocked |
| shallow below-VWAP rebound | 151 | +0.1051% | -0.1431% | -0.3970% | -0.6647% | do not chase rebound |
| near-VWAP reclaim setup | 124 | -0.0240% | -0.2219% | -0.3217% | -0.6303% | keep confirmation |
| improving-volume reclaim | 26 | +0.0649% | -0.1045% | -0.7249% | -1.6482% | reject promotion |

The apparent early rebound in shallow/improving-volume cases did not persist.
Immediate entry would have converted a small transient move into materially
negative later outcomes.

Decision:

```text
RETAIN existing reclaim confirmation.
REJECT immediate-entry relaxation.
```

### Pullback Quality

The lane was slightly negative at +5/+15 minutes and deteriorated further at
+30/+60 minutes.

The formal promotion-watch subtype was `failed_pullback`:

| Metric | Result |
| --- | ---: |
| Observed | 74 |
| Observed days | 3 |
| Sample concentration | 56.76% |
| +5m | +0.0696% |
| +15m | +0.0366% |
| +30m | -0.1621% |
| +60m | -0.5012% |
| MFE5 | +0.2754% |
| MAE5 | -0.2363% |

It technically passed the simple positive +5/+15 contract screen, but the
edge was:

- smaller than realistic transaction cost
- unstable across days
- negative after 30 minutes
- negative on June 19

Decision:

```text
REJECT PROMOTION.
Keep the existing pullback-quality gate.
```

### Opening Momentum

Observed opening candidates were negative at every checkpoint.

MFE was large, but MAE was larger. This describes unstable opening volatility,
not a robust entry edge.

Limitations:

- June 19 opening data is incomplete.
- The opening probe produced zero would-enter candidates.
- Opening large-cap surge had too few independent candidates.

Decision:

```text
Do not relax the opening gate from Q8 evidence.
Do not declare all opening momentum invalid.
Require a future decision-time baseline and a separately defined opening
evaluation contract if this area is revisited.
```

### Runner-Up Selection

Runner-up candidates were approximately flat at +5/+15 minutes and negative
afterward.

This supports the existing rule:

```text
A blocked Top-1 candidate does not automatically authorize the next rank.
Runner-up candidates require independent suitability, chart, volume, and
cost-edge checks.
```

No evidence supports cascade entry.

### Human Chart Sanity

Aggregate evidence was mixed and weak:

- negative +5 minutes
- approximately flat +15/+30 minutes
- small positive +60 minutes
- adverse excursion exceeded favorable excursion

The positive June 19 subset was too small and inconsistent with earlier days.

Decision:

```text
RETAIN the guard.
Do not weaken it from Q8 evidence.
```

### Breakout Readiness

Short-horizon results were flat to negative, while +30/+60 minute results were
positive.

This is not evidence for immediate breakout entry. It suggests a possible
horizon mismatch:

```text
blocked at T0
later structure matures
continuation occurs after additional confirmation
```

The effect changed materially by day and remained below current mock-broker
cost estimates.

Decision:

```text
No Q8 promotion.
Pass to Q9 as a delayed re-evaluation question.
```

### Volume Confirmation

The positive +30/+60 aggregate was dominated by June 18:

```text
June 18 +30m: +3.6607%
June 18 +60m: +6.0644%
```

Other days were much weaker or negative.

`delayed_volume_confirmation` had only 17 trusted observations:

| +5m | +15m | +30m | +60m |
| ---: | ---: | ---: | ---: |
| +0.1061% | +0.2094% | -0.1113% | -0.3241% |

Decision:

```text
RETAIN volume confirmation.
Do not promote a broad relaxation.
Q9 may evaluate whether delayed confirmation creates a short-lived entry
window in specific regimes.
```

## Cost Edge Finding

The policy concept is valid:

```text
Do not enter when expected gross edge cannot exceed round-trip cost plus the
required net-profit buffer.
```

The Q8 gross shadow results also do not justify removing the gate:

| Horizon | Gross Forward Return |
| --- | ---: |
| +5m | +0.0236% |
| +15m | +0.2085% |
| +30m | +0.2149% |
| +60m | +0.3105% |

These returns are below the recent observed mock-broker cost level of roughly
0.85% to 0.90%.

However, the current cost profile contains a critical implementation defect:

```text
last round-trip cost: 0.8926%
EMA round-trip cost: 0.8536%
conservative round-trip cost: 6.5539%
```

The 6.5539% value came from:

```text
2026-06-01
TRD_20260601_002870_02
```

The profile uses a permanent historical maximum:

```python
conservative = max(current_sample, ema, previous_conservative)
```

Therefore one old outlier never decays and is still applied to current
Monitor policy.

Observed runtime consequence:

```text
round-trip cost floor: 6.55%
cost-aware profit floor: 6.85%
```

This defect does not prove that the blocked cost-edge candidates were
profitable. Their average gross returns were still below the recent 0.85% to
0.90% cost level.

It does prove that:

- cost-edge gate strictness was overstated
- would-enter count was artificially suppressed
- cost-edge blocker frequency cannot be treated as pure market evidence
- the runtime cost profile must be repaired before evaluating entry scarcity

Required action:

```text
RETAIN the cost-edge rule.
REPAIR the cost-profile estimator.
REBASE the conservative floor from valid recent samples.
Do not reuse the 6.55% floor as policy evidence.
```

## Market-Regime Findings

| Market Rail | Observed | Days | +5m | +15m | +30m | +60m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| KRX night futures gap up | 1,059 | 2 | -0.0371% | -0.1300% | -0.2592% | -0.5005% |
| KRX night futures gap down | 680 | 2 | +0.0079% | +0.1131% | +0.1840% | +0.4620% |
| mixed neutral | 37 | 1 | +0.0178% | +0.3359% | +0.4780% | unavailable |
| risk-off breadth collapse | 26 | 1 | +0.1664% | +0.2635% | +0.1666% | +1.6472% |

The counterintuitive gap-down/risk-off strength likely reflects:

- intraday rebound behavior
- relative-strength candidate selection
- candidate mix differences
- only one or two days per rail

It does not prove that risk-off markets should trigger aggressive buying.

What Q8 did establish:

```text
The same blocker has different opportunity cost under different market rails.
Market rail must be a conditioning dimension in Q9, not a universal hard
permission or veto.
```

## Time-Bucket Findings

| Time Bucket | Observed | +5m | +15m | +30m | +60m |
| --- | ---: | ---: | ---: | ---: | ---: |
| opening 0-20m | 114 | -0.0312% | -0.1408% | -0.3234% | -0.2469% |
| opening 20-60m | 250 | -0.1509% | +0.0091% | +0.2744% | +0.8702% |
| mid-session | 1,284 | +0.0064% | -0.0417% | -0.1385% | -0.3319% |
| late-session | 150 | +0.0297% | +0.1720% | +0.1557% | +0.6504% |

Interpretation:

- immediate opening entries were not supported
- 20-60 minute candidates often required time before continuation
- mid-session candidate quality was poor
- late-session results were better, but still gross and below current mock
  costs at short horizons

This supports horizon-aware evaluation. It does not support a direct
time-of-day entry rule.

## Actual Trade Context

Legacy context from June 1 through June 16:

```text
45 return samples
4.44% win rate
-1.1179% average return
```

Current Q9 trusted backfill:

```text
34 eligible realized trades
5.88% win rate
-1.0550% average net return
profit factor 0.1564
```

This means Q8's defensive findings were directionally useful, but the live
system still failed to produce positive expectancy among the small set of
entries that passed.

Q8 mainly answered:

```text
Which weak candidates should remain blocked?
```

It did not answer:

```text
Which accepted candidates have a repeatable profitable edge?
```

That second question belongs to Q9.

## What Is Worth Keeping

### Keep As Official Concepts

- cost edge must exceed transaction cost
- runner-up candidates require independent suitability
- VWAP reclaim requires confirmation
- weak pullbacks remain blocked
- volume confirmation remains required
- human chart sanity remains a guard
- shadow candidates require dedupe and trusted same-day forward outcomes
- promotion requires a fixed evidence contract

### Keep As Q9 Evaluation Questions

- delayed breakout continuation after an initial block
- delayed volume confirmation as a short-lived entry window
- cost-edge outcomes by intended holding horizon
- market-rail-conditioned opportunity cost
- opening 20-60 minute continuation versus immediate opening entry
- late-session conditional performance
- accepted-candidate quality versus correctly blocked candidates

### Reject From This Q8 Window

- broad failed-pullback relaxation
- immediate entry during improving-volume VWAP reclaim
- automatic runner-up cascade
- broad opening momentum relaxation
- weakening human-chart sanity based on isolated winners

### Treat As Data Defects, Not Strategy Evidence

- 6.55% permanently sticky conservative cost floor
- June 19 missing opening runtime window
- old cross-day/stale forward observations
- raw duplicate candidate inflation
- legacy reports without the canonical trust gate

## Final Promotion Decisions

| Candidate | Decision | Reason |
| --- | --- | --- |
| failed-pullback relaxation | REJECT | edge too small, unstable, negative later |
| improving-volume reclaim entry | REJECT | +5m transient, +15m onward negative |
| broad VWAP reclaim relaxation | REJECT | large trusted sample consistently negative |
| opening momentum relaxation | REJECT FOR CURRENT CONTRACT | available evidence negative; opening data incomplete |
| runner-up cascade | REJECT | later returns weak; independent review remains necessary |
| human-chart guard relaxation | RETAIN CURRENT POLICY | mixed and insufficient benefit |
| volume gate relaxation | RETAIN CURRENT POLICY | positive long horizon driven by one day |
| breakout immediate-entry relaxation | RETAIN CURRENT POLICY | only delayed continuation signal exists |
| cost-edge hard gate concept | RETAIN | gross shadow edge remains below valid recent costs |
| current 6.55% cost profile | INVALIDATE | stale maximum outlier contaminates policy |

## Q8 Closure

Q8 is complete for the current contract.

It should not be extended merely to search for a positive result.

The next work belongs to Q9:

1. repair and version the cost profile
2. separate raw Scanner baseline from Strategist-influenced ranking
3. evaluate accepted trades against blocked candidates
4. attribute Commander and Monitor value separately
5. condition results by market rail and intended holding horizon
6. evaluate whether any component creates net value after valid costs

Final status:

```text
Q8 tactical validation: COMPLETE
New policy promotion: NONE
Existing defensive concepts: RETAINED
Relaxation candidates: REJECTED
Critical cost-profile defect: ESCALATED
Evaluation ownership: HANDED TO Q9
```
