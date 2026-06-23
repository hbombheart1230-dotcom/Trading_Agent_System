# Q9 Component Decision

Date: 2026-06-22

Canonical report:

```text
reports/evaluation/component_review/2026-06-22/q9_full_chain_component_review.md
```

Analysis range:

```text
2026-06-01 through 2026-06-22
```

## Final Historical Decisions

| Component | Decision | Conclusion |
| --- | --- | --- |
| Scanner | `ADJUST_AND_RETEST` | Top-pick ordering does not show a material advantage and all measured horizons remain cost-negative. |
| Strategist | `INSUFFICIENT_EVIDENCE` | No trusted pre-Strategist Scanner control exists. |
| Commander | `INSUFFICIENT_EVIDENCE` | No explicit final-selection/veto alternative is joined to outcomes. |
| Monitor entry | `RETAIN` | Entry timing is not the first demonstrated loss source. |
| Monitor exit | `INSUFFICIENT_EVIDENCE` | 16 post-exit observations exist; the fixed minimum is 20. |
| Full system | `REJECT` | The positive broker-net edge hypothesis is rejected for this range. |

## Scanner Evidence

The conservative observed round-trip cost was 0.9991%.

Top-pick cost-adjusted expectancy:

| Horizon | Observations | Expectancy |
| --- | ---: | ---: |
| +5m | 526 | -0.9894% |
| +15m | 524 | -0.9440% |
| +30m | 514 | -0.9400% |
| +60m | 464 | -0.9747% |

Paired Top-pick minus evaluated runner-up:

| Horizon | Paired windows | Average delta |
| --- | ---: | ---: |
| +5m | 103 | +0.1366% |
| +15m | 94 | -0.0473% |
| +30m | 100 | +0.0259% |
| +60m | 88 | -0.5768% |

The fixed materiality requirement is:

```text
average paired delta >= +0.30%
and positive-window rate >= 55%
```

No horizon passes both the relative-ranking and absolute cost-adjusted edge
requirements. A merely positive value such as +0.0259% is not treated as an
edge.

## Monitor Evidence

Entry:

- 41 matched trades across 13 days
- average actual-entry price delta: -0.6841%
- median actual-entry price delta: +0.0301%
- decision: retain current entry timing while the earlier candidate layer is
  repaired

Exit:

- 16 exits with post-exit observations across 9 days
- +5 minute average improvement: +0.1403%
- the observed improvement is too small to explain the full-system loss
- four more valid exit observations are required for the fixed directional
  minimum; no additional exit metric or horizon will be added

## Attribution Gap

Across 54 trade models:

- trusted raw Scanner controls: 0
- Strategist snapshots: 52
- explicit Commander snapshots: 0
- Scanner vs Strategist comparable records: 0
- Strategist vs Commander comparable records: 0

Historical reconstruction cannot manufacture these controls. Strategist and
Commander remain unjudged rather than being assigned fabricated value.

## Fixed Next Scope

There are no additional diagnostic components.

The remaining forward evidence work is limited to:

1. persist a trusted raw pre-Strategist Scanner Top-10
2. persist the post-Strategist ranking and selected candidate under the same
   decision ID
3. persist Commander final selection, veto, or no-trade reason
4. join all three states to the existing trusted forward-outcome machinery
5. collect four additional valid post-exit observations

After those exact gaps are filled, rerun the same component report. Do not add
new lanes, horizons, score families, or evaluation questions.

## Instrumentation Status

Implemented on 2026-06-22:

- `q9_decision_windows.json` daily append/upsert contract
- A: same-universe Scanner intrinsic Top-10
- B: post-Strategist Top-10 and selected symbol
- C: final approval/veto/no-trade outcome
- `decision_id` propagation into Q9-only forward candidates
- `+5/+15/+30/+60m` outcome join in the full-chain component review

Important boundary:

```text
A measures ranking influence within the same candidate universe.
It does not measure whether Strategist changed the candidate universe itself.
```

The universe-level Strategist comparison remains unavailable until a separate
pre-Strategist candidate-pool snapshot exists. This limitation does not block
ranking-effect evaluation and must not be silently merged with it.

## Action Boundary

The first actionable component is:

```text
scanner_candidate_quality_and_horizon_calibration
```

This document does not authorize a Scanner-weight change, entry change, exit
change, Strategist prompt change, or Commander authority change. Any behavior
proposal requires a separate promotion review.
