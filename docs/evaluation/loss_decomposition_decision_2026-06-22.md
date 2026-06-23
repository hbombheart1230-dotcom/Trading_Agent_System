# Loss Decomposition Decision

Date: 2026-06-22

Analysis range:

```text
Realized trades: 2026-06-01 through 2026-06-22
Trusted shadow forward days present in the dataset:
2026-06-16, 2026-06-17, 2026-06-18, 2026-06-19, 2026-06-22
```

Canonical generated report:

```text
reports/evaluation/decomposition/2026-06-22/full_chain_loss_decomposition.md
```

## Final Diagnosis

The first demonstrated loss of edge is candidate edge and horizon alignment.

It is not Monitor exit timing.

Evidence:

- 49 realized trades
- win rate: 10.2%
- expectancy: -0.9587%
- profit factor: 0.2307
- realized rank-1 expectancy: -1.2444%
- Top-pick shadow +15m: +0.0551%
- Top-pick shadow +30m: +0.0591%
- Top-pick shadow +60m: +0.0244%
- recent observed round-trip cost: approximately 0.85% to 0.90%
- post-exit +5m average improvement: +0.1403%

The selected Top-pick candidates do not show enough gross movement to cover
cost. Holding five minutes longer after exit improves price on average, but
the improvement is far too small to repair the realized expectancy deficit.

## Important Conditional Edge

Candidate quality differs sharply by time bucket:

| Time bucket | +15m | +30m | +60m |
| --- | ---: | ---: | ---: |
| opening 0-20m | +0.2958% | +0.0233% | -0.0506% |
| opening 20-60m | +0.4350% | +0.9284% | +2.0697% |
| mid-session | -0.1820% | -0.3118% | -0.6526% |
| late-session | +0.2333% | +0.6379% | +1.2171% |

This does not authorize immediate trading changes. It identifies a mismatch:

```text
different time-bucket and holding-horizon signals
were evaluated and executed through one short-term scalp framework
```

## Component Decisions

| Component | Decision |
| --- | --- |
| Raw candidate edge | conditional, not universal |
| Scanner Top-pick edge | economically insufficient |
| Scanner ranking | partially reconstructable only |
| Strategist value | unavailable until raw Scanner control exists |
| Commander value | unavailable until explicit alternatives exist |
| Monitor entry | not proven as primary failure |
| Monitor exit | secondary; cannot rescue current deficit |
| Full system | negative |

## Fixed Next Target

Priority 1:

```text
candidate_edge_and_horizon_alignment
```

Required next analysis:

1. separate candidate performance by time bucket
2. separate intended holding horizon
3. compare opening 20-60 minute continuation with 30-60 minute outcomes
4. identify why mid-session candidates continue to enter the selection funnel
5. preserve raw Scanner control before judging Strategist

Do not tune entry thresholds and exits simultaneously.

Do not loosen Q8 guards globally.

Do not promote opening continuation from this aggregate alone. First produce
trusted raw Scanner and decision-window comparisons under Q9.

## Why Q8 Did Not Find This Clearly

Q8 primarily evaluated whether existing blockers should be relaxed.

It grouped evidence by blocker and lane, but it did not make the following the
primary decision sequence:

```text
candidate gross edge
-> ranking value
-> Strategist/Commander delta
-> entry timing loss
-> exit timing loss
```

That evaluation-order mistake is now corrected by the loss-decomposition
report and the Q9 full-chain matrix.
