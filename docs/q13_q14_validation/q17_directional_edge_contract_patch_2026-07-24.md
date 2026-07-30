# Q17 Horizon Directional Edge Contract Patch - 2026-07-24

## Decision

`APPLY_ONE_BEHAVIOR_PATCH`

Q17 supplies the Monitor cost filter with empirical, horizon-matched
directional expectancy. It does not relax Q16 and does not permit ATR,
volatility, or a desired take-profit level to act as directional evidence.

## Root Cause

On 2026-07-24:

- Commander approved 319 windows.
- Monitor produced 36 triggered entry setups among approved windows.
- Every approved candidate lacked `directional_edge_evidence`.
- Every approved candidate lacked `estimated_gross_edge`.
- Q16 had zero directional-admitted candidates across its exact evidence days.

The cost filter supported explicit expected-move fields, but the runtime did
not have a producer for those fields.

## Module

`libs/runtime/monitor_directional_edge.py`

Inputs:

- Strategist horizon
- Monitor setup reason
- monthly strategy-memory shadow outcomes

Horizon mapping:

| Strategy Horizon | Evidence Horizon |
| --- | --- |
| scalp | +5m |
| intraday | +30m |
| overnight_probe | next session open |
| 1_2day_swing | +1 trading day |

The long-horizon rows require matching `avg_return_next_open_pct` and
`avg_return_1d_pct` evidence. The current monthly shadow aggregate does not
yet publish those fields, so these horizons fail closed. A +60m return is an
intermediate observation and cannot authorize an overnight or 1-2 day trade.

Eligibility:

- positive historical expectancy
- at least 20 observed rows
- at least 5 observed days
- coverage at least 70%
- sample concentration no greater than 70%

A low-coverage profile may be used only when it has at least 100 observations,
10 observed days, and concentration no greater than 50%. The override is
recorded explicitly.

The resulting percent value is converted to a ratio and passed as
`metrics.expected_move_pct`. The existing cost filter still applies quality
haircut, cost floor, multiplier, and minimum net buffer.

## Current Data Check

The monthly VWAP-reclaim profile has:

- 641 observed candidates
- 11 observed days
- 27.7% coverage
- 29.0% concentration
- +30m average return: 0.0852%

It qualifies for the high-volume evidence override, but its directional edge
is far below the current required gross edge of 1.65%. It remains blocked with
`estimated_gross_edge_below_cost_floor`, rather than the incorrect
`directional_edge_evidence_missing`.

This patch therefore repairs the contract without forcing a trade.

## Q9 Forward Integrity

Q9 now preserves the compact Scanner price snapshot in each additive decision
record. When minute rows are unavailable, reporting may construct a
same-symbol Scanner snapshot price series for forward checkpoints.

This addresses the recurring `minute_rows_unavailable` cause for candidates
that were ranked but never selected by Monitor.

The 2026-07-24 day remains `INVALID`: 465 historical non-selected candidate
rows have no recoverable price in either minute data or the canonical Scanner
artifact, leaving forward usable coverage at 75.47% versus the fixed 95%
requirement. The repair process reuses canonical selected-candidate prices
where present, but it does not invent missing historical prices or override
day validity. The additive snapshot fix applies from the next runtime session.

The single incomplete 2026-07-24 P/A/B window cannot be reconstructed because
its downstream Commander event was never produced. It remains visible as
linkage coverage `622/623`; no synthetic decision is created.

## Validation

For the next three full trading days, record:

- directional estimate available count
- evidence source and horizon
- cost-filter pass count
- below-cost directional estimate count
- missing directional estimate count
- +5m/+15m/+30m live-net outcomes by evidence source
- Q9 forward usable coverage

Do not change Scanner, Strategist, Commander, entry signal, exit, or order
logic during this window. Q17 may be retained only if admitted evidence is
traceable and does not reintroduce proxy-only false positives.

## Observability Repair - 2026-07-28

The first two Q17 days exposed an artifact propagation defect:

- Q9 stored `monitor_intent=NOOP` but discarded the Monitor reason.
- Quant shadow rows stored the cost-filter result but discarded the
  `directional_edge_estimate` that produced it.
- Q16 could therefore identify proxy-only rejection, but Q17 could not
  distinguish eligible directional evidence below cost from unavailable
  evidence.

The repair is additive and does not change trading behavior:

- Q9 `commander_final.monitor_observation` now preserves Monitor reason,
  trigger/guard state, cost-filter failures, and directional estimate.
- Quant shadow top-pick and runner-up rows preserve
  `directional_edge_estimate`.
- Q17 reporting separates:
  - `DIRECTIONAL_ADMITTED`
  - `DIRECTIONAL_BELOW_COST_REJECTION`
  - `DIRECTIONAL_EVIDENCE_UNAVAILABLE`
  - `DIRECTIONAL_ESTIMATE_ARTIFACT_MISSING`
  - `DIRECTIONAL_AVAILABLE_OTHER_BLOCK`

Q16's final `RETAIN` decision and its original cohorts remain unchanged.
Historical directional estimates are not inferred. The 38 triggered rows from
2026-07-27 through 2026-07-28 that did not store the estimate are explicitly
classified as `DIRECTIONAL_ESTIMATE_ARTIFACT_MISSING`.

The 2026-07-28 Q9 artifact was repaired only from retained shadow evidence.
Monitor NOOP reasons were recovered for 613 windows; no missing directional
estimate was synthesized.

## Runtime Contract Correction - 2026-07-29

Two implementation defects were found during the Q8-Q17 close review:

- Q17 read only a top-level `strategist_output_cache`, while live runtime
  stores the cache under `persisted_state` and normally hydrates
  `strategist_output`.
- `1_2day_swing` was absent from the evidence map and silently inherited the
  intraday +30m field. Overnight was represented by +60m, which is not
  horizon-matched evidence.

The reader now resolves memory in authoritative runtime order:

1. `strategist_output.memory_packets`
2. compatibility top-level `strategist_output_cache.output.memory_packets`
3. `persisted_state.strategist_output_cache.output.memory_packets`

Unknown horizons no longer inherit intraday evidence. Overnight and swing
require next-open and +1-day evidence respectively; until those aggregates
exist they remain unavailable and cannot satisfy the entry cost filter.

This correction does not alter the Commander-owned holding windows or
overnight approval policy. It only prevents short checkpoints from being
misrepresented as long-horizon directional evidence.
