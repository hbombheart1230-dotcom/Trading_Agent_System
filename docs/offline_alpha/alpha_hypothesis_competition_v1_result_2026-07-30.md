# Alpha Hypothesis Competition v1 Result

## Final Decision

All three hypotheses are `REJECT`.

No hypothesis is eligible for shadow integration. No live behavior was
changed.

## Evidence Integrity

| Measure | Result |
| --- | ---: |
| Raw candidate rows | 47,376 |
| Canonical candidate snapshots | 14,363 |
| Historical symbols required | 102 |
| Historical symbols complete | 102 |
| Historical provider errors | 0 |
| Cost | 0.28% |
| Primary horizon | +30m |

Forward results were reconstructed directly from Kiwoom historical one-minute
candles. The result does not depend on the sparse forward fields previously
retained in Q8/Q9 artifacts.

## Comparison

| Hypothesis | Train observed | Train coverage | Train live net | Train PF | Validation observed | Validation coverage | Validation live net | Validation PF | Validation win rate | Positive days | Validation MDD | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| H1 Opening Risk-Off Reclaim | 21 | 100.00% | +0.3197% | 1.3361 | 46 | 90.20% | -0.0385% | 0.9267 | 47.83% | 50.00% | -9.8046% | REJECT |
| H2 Confirmed Volume Breakout | 86 | 85.15% | -1.1562% | 0.2607 | 101 | 86.32% | +0.2605% | 1.4158 | 30.69% | 31.58% | -20.9323% | REJECT |
| H3 Confirmed VWAP Pullback | 20 | 95.24% | +0.8570% | 2.3431 | 28 | 87.50% | +0.0640% | 1.1254 | 42.86% | 35.29% | -6.2361% | REJECT |

## Interpretation

### H1 Opening Risk-Off Reclaim

June looked positive, but July did not reproduce the edge. Validation
expectancy, profit factor, positive-day ratio, and MDD all failed. A weak
opening plus near-VWAP recovery is not sufficient by itself.

### H2 Confirmed Volume Breakout

July's positive average is dominated by a minority of large winners. The
30.69% win rate, 31.58% positive-day ratio, and -20.93% cumulative MDD show
that the rule is unstable. June was strongly negative, so the train and
validation direction also disagrees.

### H3 Confirmed VWAP Pullback

This is the closest candidate, but it still fails the frozen contract. July
expectancy is only +0.0640% after cost, profit factor is below 1.20, positive
days are only 35.29%, and MDD is slightly worse than -6%. The June edge did
not remain strong enough out of sample.

## Closed Actions

- do not relax thresholds
- do not extend the evaluation period automatically
- do not connect any hypothesis to live or shadow runtime
- preserve the cache, code, and report as reproducible rejected baselines
- do not create another numbered live validation phase from this result

## What This Establishes

Simple binary combinations of the current Monitor factors do not provide a
stable cost-adjusted edge across June and July.

The next research direction, if continued, must not be another small threshold
variation of these three rules. It should address one of the structural
limitations:

- full-market or stable point-in-time universe construction
- cross-sectional ranking rather than isolated yes/no conditions
- explicit target/stop path simulation instead of a fixed forward horizon
- market and sector relative-strength synchronization

Generated artifacts:

- `reports/evaluation/offline_alpha/alpha_hypothesis_competition/2026-06-01_2026-07-30/alpha_hypothesis_competition_v1.json`
- `reports/evaluation/offline_alpha/alpha_hypothesis_competition/2026-06-01_2026-07-30/alpha_hypothesis_competition_v1.md`
