# Tactical Operating Baseline

Last updated: 2026-05-21

## Purpose

This document is the standing reference for trading tactic changes. It exists
to prevent ad hoc patches from changing multiple layers at once without a clear
baseline.

The current priority is not to increase trade count. The priority is to stop
repeating negative-expectancy entry/exit combinations while keeping enough
observability to decide the next controlled change.

## Current Weekly Baseline

Source: `reports/operator_summary/weekly/2026-W21/weekly_summary.json`

- Period: 2026-05-18 to 2026-05-24
- Trades: 33
- Closed trades: 32
- Win rate: 7.69%
- Average return: -1.27%
- Average hold time: 850.5 sec
- Return basis: truth-surface net

2026-05-21 intraday check:

- Daily summary at the latest refresh showed 8 total trades, 6 closed trades,
  50.00% win rate, and -0.41% average return.
- Weekly summary after today's trades showed 41 total trades, 38 closed trades,
  15.62% win rate, and -1.11% average return.
- Today's improvement in win rate does not yet prove a behavior unlock. Two
  034220 fixed-stop losses dominated the negative average.
- Post-exit shadow recap refreshed 6 trades and observed all 6. EOD remains
  pending intraday. Use this as observation-only evidence.

Hold-time distribution observed from symbol trade histories:

- `<1m`: 5
- `1-5m`: 11
- `5-15m`: 7
- `15-30m`: 7
- `30-60m`: 1
- `1-4h`: 2
- `4h+`: 0

## Current Tactical Findings

### Entry

- Dominant strategist setup is `vwap_reclaim_pullback`.
- `vwap_reclaim_pullback`: 19 trades, win 6.2%, avg -1.27%.
- `defensive_observe`: 14 trades, win 10.0%, avg -1.27%.
- Scanner rank did not rescue performance:
  - rank1: 10 trades, win 12.5%, avg -1.15%.
  - rank2-3: 11 trades, win 0.0%, avg -1.28%.
  - rank4-10: 11 trades, win 10.0%, avg -1.36%.
- Human chart score is currently better as a veto than as a positive entry
  signal. High scores did not yet show reliable positive expectancy.
- Scanner chart fit is mostly `soft_rank_bias_only`, so it is not yet a hard
  quality gate.

2026-05-21 check:

- Most live entries still came from "top candidate blocked -> runner-up
  reassessment" rather than clean rank1 entry.
- Runner-up outcomes were mixed:
  - 024840 rank9 / scanner chart-fit 0.132 / profit.
  - 012330 rank2 / scanner chart-fit 0.449 / profit.
  - 034220 rank5 / scanner chart-fit 0.477 / loss.
  - 006345 rank4 / scanner chart-fit 0.400 / profit.
  - 233740 rank3 / scanner chart-fit 0.560 / loss.
  - 034220 rank2 / scanner chart-fit 0.189 / loss.
- Therefore scanner chart-fit must remain diagnostic. Do not promote it to a
  standalone hard veto.
- The next runner-up check should be independent tactic fit plus cost edge plus
  monitor readiness, not chart-fit alone.

### Exit

- `intraday_low_break` is the main loss cluster:
  - 16 trades, win 0.0%, avg -1.15%, avg hold 384 sec.
- Fixed stop loss:
  - 7 trades, win 0.0%, avg -2.34%.
- VWAP breakdown:
  - 4 trades, win 0.0%, avg -1.44%.
- Cost floor matters:
  - `cost_floor_state=not_met`: 29 trades, win 0.0%, avg -1.39%.
  - `cost_floor_state=met`: 2 trades, win 100%, avg +0.15%.

## Active Tactical Baseline

### Strategist

- Allowed tactical families:
  - `vwap_reclaim_pullback`
  - `defensive_observe`
  - lower VWAP rebound probe as a narrow monitor path only
- Do not reintroduce `leader_vwap_reclaim_pullback` as a single umbrella
  strategy. Keep subtype evidence explicit.
- Strategist LLM cache should be reused unless there is actionable entry
  readiness or a strong new rank1 outside the cached frame.

### Scanner

- Do not penalize symbols by name.
- Memory/semiconductor concentration should be handled through state
  classification, not symbol penalties:
  - repeated market-representative candidate
  - same blocker cluster
  - weak theme/news confirmation
  - cost floor not met
- Chart fit is currently advisory. Promotion to hard veto requires a separate
  patch and before/after evidence.

### Monitor Entry

Hard-veto candidates:

- `cost_floor_state=not_met`
- `directional_edge_evidence_missing`
- `volume_confirmation_missing`
- `same_symbol_position_open`
- `human_chart_entry_score < 0.50` when not explicitly covered by a narrow
  exception

Current narrow exception:

- `lower_vwap_rebound_probe_path`
  - only below VWAP shallow band
  - no breakout path
  - higher lows
  - rebound confirmed
  - relaxed volume floor met
  - confidence floor met
  - still blocked by true risk signals such as swing-low break, lower-high
    failure, and high exit risk

Runtime status as of 2026-05-21:

- Some entry guard behavior is already live-affecting through commander/monitor
  enforcement. Treat this as a controlled behavior patch, not Q1-Q7
  observation-only infrastructure.
- Quant tactic suitability and factor snapshots remain observation-only.
- `ai_trade_summary_input.json` now carries `quant_tactic` so Q8 validation can
  compare trade-level diagnostics with operator summary aggregation.
- If operator summary says `Quant entry blockers: none`, verify whether that
  means every executed trade passed the quant entry decision, or whether the
  executed trade report lacks entry-time quant decision capture.

### Monitor Exit

Hard exits stay hard:

- broker truth mismatch
- hard stop
- liquidity collapse
- data quality failure
- market regime flip with explicit risk evidence

Non-hard exits should require confirmation when the trade horizon is intraday:

- VWAP breakdown
- intraday low break
- minor pullback after entry

The current loss cluster says `intraday_low_break` should not be allowed to
operate as a one-tick early noise exit unless it is a hard stop equivalent.

### Horizon And Carry

Supported horizons:

- `scalp`
- `intraday`
- `overnight_probe`
- `1_2day_swing`

Current runtime state:

- Long horizons are still capped to `intraday` during live validation.
- Horizon metadata is mostly observability-only.
- `do_not_force_hold=True` means horizon intent must not force holding.

Long-horizon behavior should not be enabled until post-exit shadow shows that
longer holding would have improved results for a stable subset.

2026-05-21 post-exit read:

- 012330 would have improved materially through +60m, but 233740 and 034220_02
  weakened after exit.
- This is not enough to unlock long-horizon behavior globally.
- Continue splitting post-exit evidence by tactic ID, exit reason, hard-stop
  status, and cost floor state before changing hold/carry behavior.

Candidate unlock criteria:

- post-exit EOD or +60m improvement in at least 60% of a defined subset
- hard stop would not have been hit first
- cost floor met at entry
- market regime not risk-off, or inverse/hedge-specific rule is active
- no broker restriction or execution uncertainty

## Patch Queue

### Immediate: Q8 Artifact Integrity

Fix and verify report fields before promoting any new behavior:

- Trade summary must show actual symbol name, not scanner reason text or score
  text.
- Trade summary must show exact symbol themes only when symbol-specific theme
  evidence or an explicit fallback exists.
- Trade summary input must include `quant_tactic` so trade-level Q8 inspection
  and operator summary aggregation use the same evidence.
- Post-exit shadow recap must refresh individual trade summaries through the
  runtime triggers and the closeout recap.

Done on 2026-05-21:

- Blocked score/runner-up explanation text from being used as symbol names.
- Added fallback metadata for 012330, 034220, and 024840.
- Added `quant_tactic` to `ai_trade_summary_input.json`.
- Regenerated 2026-05-21 post-exit recap and affected trade summaries.

### Immediate: Runner-Up Independent Fit Review

Do not add a hard gate yet. First verify these fields exist for each runner-up
entry:

- top candidate blocked reason
- actual selected rank and scanner score
- tactic suitability tier and score
- cost edge / cost floor state
- monitor entry quant decision and blockers
- scanner chart-fit score
- entry guard decision and override reason, if any

Promotion candidate after verification:

- runner-up entry allowed only when tactic suitability is not weak, cost edge
  is acceptable, and monitor readiness is explicit.
- scanner chart-fit may contribute to the review but must not be the only
  blocker.

### Next: Weekly Summary Observability

Add the following to weekly markdown:

- hold-time distribution
- exit reason table with count, win rate, avg return, avg hold
- cost-floor performance table
- human-chart score/setup buckets
- strategy horizon source vs commander-applied horizon
- long-horizon cap count and reason

Reason: the JSON already contains most signals, but the markdown hides the
main diagnosis.

### Next: Early Exit Loss Cluster

Add an explicit `early_exit_loss_cluster` section:

- `intraday_low_break` under 60 sec
- `intraday_low_break` under 5 min
- loss exits before strategy min hold
- repeated same playbook + exit reason losses

Reason: the dominant loss mechanism is short-hold exits, not lack of long-hold
intent.

### Post-Q8 Candidate Behavior Patch: Cost Floor Hard Gate

Promoted. `cost_floor_state=not_met` / `cost_edge_fail` is a pre-entry hard
veto, unless an explicit commander override exists.

Q8 now evaluates this on the shadow surface instead of waiting for actual
closed-trade samples. That is intentional: cost-edge is known before order
placement, so shadow candidates are valid evidence for whether the guard would
have blocked weak entries.

Required evidence for continued operation:

- verify current monitor has cost floor state at entry time
- verify BUY exceptions are documented in commander reason
- verify trade report summary shows veto reason
- daily summary shows `Q8 shadow readiness` and
  `already_promoted_monitor_hard_gate` when the cost-edge shadow signal is
  ready and the monitor hard gate is already active

### Post-Q8 Strategist Lane Rebalance

Promoted as strategist input guidance, not as a scanner/monitor override.

When operator summary shows weak or poor `vwap_reclaim_pullback` lane
selection and Q8 shadow diagnostics show breakout-ready-like candidates, the
next strategist LLM payload must include `tactic_lane_guidance`:

- downweight repeated `vwap_reclaim_pullback` unless cost, volume, and
  pullback maturity are all ready
- explicitly score `breakout` / `volume_breakout` against pullback before
  choosing the tactical strategy
- keep promoted cost-edge guard intact when Q8 shadow readiness recommends it

Authority owner: strategist. Commander still controls policy application,
scanner still selects candidates, and monitor still confirms entry/exit.

### Post-Q8 Candidate Behavior Patch: Human Chart Hard Veto

Promote `human_chart_entry_score < 0.50` to hard veto except for explicitly
listed probe modes.

Required evidence before patch:

- confirm score availability on live candidate snapshots
- confirm no conflict with lower VWAP rebound probe exception
- confirm report shows the blocked feature

### Post-Q8 Candidate Behavior Patch: Long Horizon Unlock

Do not enable yet. Keep observability-only until post-exit shadow has enough
evidence.

## Change Discipline

Each behavior patch must state:

- target failure cluster
- exact fields used
- authority owner: strategist, commander, scanner, monitor, or reporter
- expected reduction in bad trades
- expected side effect
- rollback trigger
- tests run

Do not bundle unrelated entry, exit, cache, and reporting changes in one patch.
