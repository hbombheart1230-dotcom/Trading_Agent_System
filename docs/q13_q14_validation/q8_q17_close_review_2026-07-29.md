# Q8-Q17 Close Review - 2026-07-29

## Decision

This review closes the open-ended interpretation of Q8 through Q17.

```text
Q8: CLOSED - no tactic promoted
Q9: DIAGNOSIS COMPLETE - system and candidate edge remain cost-negative
Q10: RETAIN AS CONTROL - fixed large-cap baseline is not profitable
Q11: RETAIN AS CONTROL - opening probe v0 is not profitable
Q12: RETAIN AS CONTROL - BTC/Woori baseline is not profitable
Q13: FROZEN - attribution framework is valid when realized trades exist
Q14: FROZEN - structural attribution remains diagnostic, not causal proof
Q15: RETAIN - narrow runner-up filtering patch retained
Q16: RETAIN - ATR/volatility proxy must not count as directional edge
Q17: CONTRACT_REPAIRED - live memory path and long-horizon evidence corrected
```

No additional evaluation axis is authorized.

## Trusted Data

- Review range: 2026-06-01 through 2026-07-29
- Scanner candidate rows: 61,614
- Independent 15-minute Scanner episodes: 13,788
- Realized first entries: 72
- Realized same-day/same-symbol repeat entries: 27
- 2026-07-29 Q9 windows: 525
- Complete 2026-07-29 P/A/B/C windows: 493
- 2026-07-29 forward usable coverage: 98.63%
- 2026-07-29 validity: `VALID`

Repeated decision windows are not treated as independent trades.

## Q8

Q8 remains closed.

- Broad VWAP reclaim relaxation: rejected.
- Broad pullback relaxation: rejected.
- Broad opening momentum relaxation: rejected.
- Automatic runner-up substitution: rejected.
- Cost, reclaim, volume, pullback, and human-chart guard concepts: retained.
- New profitable tactic: none.

Q8 artifacts remain evidence inputs only.

## Q9

Q9 established that the main problem is absolute candidate edge, not only
agent orchestration.

Episode-level live-cost results:

| Rank | +5m | +15m | +30m |
| --- | ---: | ---: | ---: |
| Rank 1 | -0.2169% | -0.2265% | -0.3749% |
| Rank 2-3 | -0.3618% | -0.3878% | -0.2934% |
| Rank 4+ | -0.3718% | -0.4162% | -0.3119% |

Rank 1 is relatively better at 5 and 15 minutes, but it is not profitable
after estimated live cost. Changing ranking weights is not authorized because
score-component coverage is only 18.4%.

Strategist B minus Scanner A:

| Horizon | Observed Days | Average Delta |
| --- | ---: | ---: |
| +5m | 25 | -0.0019% |
| +15m | 25 | -0.0594% |
| +30m | 25 | -0.0318% |
| EOD | 21 | -0.2659% |

The Strategist has not demonstrated measurable ranking alpha. The deltas are
small or negative, so the result supports a future guard review but not removal
of the Strategist.

Commander C often looks less negative because rejected windows are assigned a
cash return of zero. This is defensive value, not paired causal alpha.

## Q10-Q12 Controls

Cost-adjusted cumulative shadow results:

| Control | Sample | +5m | +15m | +30m | EOD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q10 Samsung/Hynix | 431 entries / 15 days | -1.1660% | -1.1518% | -1.0914% | -0.8669% |
| Q11 Opening Probe v0 | 66 trades / 26 days | - | - | -1.3618% realized policy result | - |
| Q12 BTC/Woori | 177 entries / 23 days | -1.2379% | -1.2846% | -1.3606% | -1.4947% |

The controls do not reveal a simple replacement strategy. The recent
three-day no-trade period is therefore not, by itself, evidence that the main
system should have traded more.

## Q13-Q14

Q13 and Q14 remain frozen.

On zero-trade days, realized-trade attribution is correctly
`INSUFFICIENT_EVIDENCE`. Q9 no-trade and shadow reports must be used instead.

`Scanner Ranking Failure` remains an outcome-conditioned label and cannot
independently authorize a Scanner patch. The largest structural historical
result is `Candidate Filtering`.

## Q15

Q15 remains `RETAIN`.

- Lower-ranked cascade entries are restricted.
- `volume_insufficient` was removed only from the anticipated pre-veto.
- Monitor's current-data volume gate remains active.
- No broad runner-up or volume relaxation is authorized.

## Q16

Q16 remains `RETAIN`.

From 2026-07-22 through 2026-07-29:

- exact proxy-only rejections: 132
- +30m observations: 128
- observed days: 5
- positive days: 1
- +30m live-net average: -0.2478%
- +30m live-net profit factor: 0.6554

ATR and volatility must remain magnitude evidence only. They must not satisfy
directional cost edge.

## Q17 Contract Repair

Q17 was intended to read monthly strategy-memory outcomes and provide
horizon-matched directional expectancy to Monitor.

The runtime contract was broken:

- the persisted cache is stored under
  `persisted_state.strategist_output_cache`
- cache hydration exposes its output as `state.strategist_output`
- `monitor_directional_edge._performance_memory` reads only
  `state.strategist_output_cache`

Therefore the profile lookup returned
`matching_performance_profile_missing` even when the profile existed.

Observed Q17 classes:

- `DIRECTIONAL_ESTIMATE_ARTIFACT_MISSING`: 38 historical rows
- `DIRECTIONAL_EVIDENCE_UNAVAILABLE`: 16 current rows
- `DIRECTIONAL_BELOW_COST_REJECTION`: 0
- `DIRECTIONAL_ADMITTED`: 0

Deterministic replay with the same retained memory proves the defect:

| Setup | Runtime Shape | Correct Cache Shape |
| --- | --- | --- |
| breakout | profile missing | ineligible: negative history and low coverage |
| pullback | profile missing | eligible evidence, but only +0.0119% gross expectation |
| lower-VWAP rebound | profile missing | eligible evidence, but only +0.0119% gross expectation |
| human-chart setup | profile missing | ineligible: negative and insufficient history |

The defect was repaired without changing the cost threshold, entry signal,
exit signal, or Commander holding policy:

```text
CONTRACT_REPAIRED
```

The memory reader now follows the live state structure and retains a
compatibility fallback for older fixtures. Deterministic replay against the
retained 2026-07-29 state resolves the VWAP reclaim profile correctly.

The replay also exposed a separate horizon mismatch:

- `scalp` correctly uses +5m evidence.
- `intraday` correctly uses +30m evidence.
- `overnight_probe` previously used +60m evidence.
- `1_2day_swing` was absent and silently fell back to intraday +30m.

The last two paths now fail closed unless next-session-open or +1-day outcome
evidence exists. The operational holding contract remains 15 minutes, 4
hours, 1 day, and 2 days maximum by horizon; 5m/30m/60m were Q17 evidence
checkpoints, not holding limits.

This is a defect repair, not a new evaluation program.

## Current No-Trade Interpretation

On 2026-07-29:

- Commander approved 315 windows.
- Monitor produced 519 NOOP decisions.
- Main reasons were:
  - below-VWAP reclaim not ready: 379
  - pullback not mature: 42
  - volume confirmation missing: 38
  - cost-adjusted edge not ready: 16
- Q11 produced five virtual entries with -2.0618% average net return.
- Q10 was negative at every horizon.

The day contains both defensive success and possible over-filtering. It does
not support broad relaxation. The 16 cost-edge cases must be reclassified
after the Q17 state-path repair.

## Next Work

### Completed Defect Repair

Q17 memory resolution now reads, in order:

1. `state.strategist_output.memory_packets`
2. `state.strategist_output_cache.output.memory_packets`
3. `state.persisted_state.strategist_output_cache.output.memory_packets`

Requirements:

- no synthetic historical estimates
- preserve Q16
- preserve cost thresholds
- deterministic replay of 2026-07-29: passed
- targeted horizon/directional regression: passed
- one full live-day contract smoke test remains; this is not another
  open-ended three-day window

### Next Behavior Review Candidate

After Q17 contract verification, the first bounded review candidate is:

```text
same_symbol_loss_reentry_control
```

Evidence:

| Cohort | Count | Win Rate | Expectancy | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| First entry | 72 | 13.9% | -0.8506% | 0.3072 |
| Repeat entry | 27 | 3.7% | -1.2478% | 0.0026 |

Repeat entries underperform first entries by -0.3972%. However, the current
read model groups every later same-day/same-symbol trade as a repeat. It does
not yet prove that the preceding trade was a loss, that the setup was
unchanged, or that a cooldown would have prevented the damage.

Before any behavior patch, decompose the retained trades by:

- preceding trade result
- elapsed minutes since exit
- same versus changed tactic/setup/horizon
- repeat sequence number
- market rail

Only a repeated loss-conditioned cohort may authorize a reentry control.
This review should be completed from existing artifacts and must not require
another open-ended live window.

### Research Candidate, Not Production

Confirmed post-reclaim pullback has 25 observations across 13 days:

- +5m live net: +0.0414%
- +15m live net: +0.1975%
- +30m live net: +0.2587%
- +60m live net: +0.2663%

It remains shadow research because the edge is small, mock-cost negative, and
not yet a production-quality independent sample.

## Final Boundary

Do not start a new open-ended evaluation axis. Q18 is subsequently defined only
as the bounded promotion review for the confirmed post-reclaim-pullback
subtype; see `q18_post_reclaim_promotion_review_plan_2026-07-30.md`.

The sequence is:

```text
Q17 state-path defect repair
-> deterministic historical replay
-> one full live-day contract verification
-> close Q17 as RETAIN or ROLL_BACK
-> decompose same-symbol repeats from existing artifacts
-> select at most one evidence-backed behavior patch
```
