# Strategy Detail And Candidate Watch Policy

Date: 2026-05-06

Status: Phase 1 visibility patch implemented; Phase 2/3 Commander execution bridge implemented; Phase 4 reporting visibility implemented

## Purpose

The prior strategist-output patches improved explanation quality:

- `strategy_adjustment_directives`
- `strategy_refresh_trace`
- deterministic `strategist_summary.md/json`
- structured scanner and monitor handoff visibility

Those surfaces make the strategist easier to inspect, but they do not yet make the strategist's tactical detail directly drive how many scanner candidates are watched by the monitor.

This patch plan connects strategist detail to Commander-owned entry participation.

## Current Gap

Current runtime already has these pieces:

- Strategist selects one coarse playbook: `breakout`, `pullback`, `reversal`, or `defensive`.
- Strategist emits `strategy_adjustment_directives`, but this is mostly an explanation/action surface.
- Commander emits `entry_control.max_priority_rank` and `entry_control.max_runner_ups`.
- Scanner exposes visible ranked candidates using the Commander scope.
- Monitor can review runner-up candidates when the top scanner pick is blocked for an eligible reason.

The missing connection is:

- Strategist does not explicitly propose how deep Scanner/Monitor should watch the ranked candidate list.
- Commander expansion is driven mostly by repeated blocker feedback, not by the chosen tactical strategy.
- Reports do not show `pre_llm_playbook`, `llm_requested_playbook`, and `final_playbook` separately.
- Reports do not show alternative strategy scores or rejected strategy reasons.

## Design Principle

Do not replace the existing contracts. Add bounded fields that can first be logged, then consumed.

Ownership:

- Strategist proposes strategy detail and candidate watch depth.
- Commander clamps and finalizes the executable candidate watch scope.
- Scanner ranks candidates and exposes only the approved watch window.
- Monitor evaluates the top pick first, then runner-up candidates only when Commander allows cascade and the block reason is eligible.
- Reporter shows the proposal, Commander clamp, and final effective scope separately.

## Additive Strategist Fields

The strategist output should add:

```json
{
  "pre_llm_playbook": "defensive",
  "llm_requested_playbook": "pullback",
  "final_playbook": "pullback",
  "tactical_strategy": "leader_vwap_reclaim_pullback",
  "strategy_scores": {
    "opening_gap_momentum": 0.42,
    "opening_range_breakout": 0.38,
    "leader_vwap_reclaim_pullback": 0.71,
    "volume_breakout": 0.44,
    "reversal_reclaim": 0.27,
    "cost_aware_scalp": 0.33,
    "defensive_observe": 0.31
  },
  "rejected_strategy_reasons": {
    "opening_gap_momentum": "open gap was not supported by breadth and follow-through",
    "opening_range_breakout": "breakout confirmation was weaker than pullback reclaim evidence",
    "defensive_observe": "market was not risk-off and liquidity remained supportive"
  },
  "candidate_watch_policy": {
    "max_priority_rank": 5,
    "max_runner_ups": 4,
    "cascade_enabled": true,
    "cascade_allowed_reasons": [
      "too_extended_from_vwap",
      "breakout_not_ready",
      "volume_insufficient",
      "below_vwap_reclaim_not_ready",
      "pullback_below_vwap_reclaim_not_ready"
    ],
    "cascade_blocked_reasons": [
      "cost_filter_failed",
      "risk_policy_block",
      "closeout_window",
      "open_position_present",
      "daily_loss_limit",
      "broker_truth_mismatch",
      "data_quality_guard"
    ],
    "reason": "pullback frame should monitor several liquid reclaim candidates but avoid risk/cost-driven fallback"
  }
}
```

These fields are additive. Existing `playbook`, `monitor_entry_policy`, `strategy_adjustment_directives`, `strategy_refresh_trace`, and `strategy_policy` remain authoritative until Commander consumes the new watch proposal.

## Tactical Strategies

Initial tactical strategies should be intentionally small:

| Tactical strategy | Parent playbook | Intended use |
| --- | --- | --- |
| `opening_gap_momentum` | `breakout` | Opening gap with follow-through and liquidity support |
| `opening_range_breakout` | `breakout` | Opening range high breakout with volume confirmation |
| `volume_breakout` | `breakout` | Strong volume expansion and new intraday high structure |
| `leader_vwap_reclaim_pullback` | `pullback` | Liquid leader or theme candidate pulling back and reclaiming VWAP |
| `reversal_reclaim` | `reversal` | Oversold or failed-breakdown candidate reclaiming VWAP/support |
| `cost_aware_scalp` | `pullback` or `breakout` | Short-horizon trade only when expected gross edge clears cost floor |
| `defensive_observe` | `defensive` | No-trade or narrow-watch mode under weak/risk-off evidence |

`defensive` must not mean frequent small trades with quick exits. It should mean reduced participation unless the expected edge is strong enough.

## Candidate Watch Mapping

Default proposal by strategy:

| Strategy | max_priority_rank | Cascade behavior |
| --- | ---: | --- |
| `defensive_observe` | 1-3 | Usually disabled. No fallback on cost/risk blocks. |
| `leader_vwap_reclaim_pullback` | 5 | Allow runner-up review for reclaim, volume, or overextension blockers. |
| `opening_gap_momentum` | 7-10 | Allow broader scan while the opening tape is strong. |
| `opening_range_breakout` | 7-10 | Allow runner-up review for top-pick overextension or breakout-not-ready. |
| `volume_breakout` | 7-10 | Allow broader monitoring of high-volume candidates. |
| `reversal_reclaim` | 3-5 | Keep shallow because reversal failure risk is high. |
| `cost_aware_scalp` | 3-5 | Disable cascade when expected edge does not clear costs. |

Commander should clamp these proposals:

| Runtime condition | Clamp |
| --- | --- |
| `risk_off` | max 1-3 candidates |
| `neutral` | accept strategy default unless guardrails object |
| `risk_on` | allow breakout/pullback depth up to 7-10 |
| open position exists | no new-entry expansion |
| closeout window | no new-entry expansion |
| preflight blocked | no new-entry expansion |
| daily loss limit near or breached | 1 candidate or no trade |
| broker/data truth mismatch | no cascade |

## Cascade Eligibility

Cascade may continue to runner-up candidates only for timing/fit blockers:

- `too_extended_from_vwap`
- `breakout_not_ready`
- `volume_insufficient`
- `below_vwap_reclaim_not_ready`
- `pullback_below_vwap_reclaim_not_ready`

Cascade must stop on risk, cost, truth, or lifecycle blockers:

- `cost_filter_failed`
- `risk_policy_block`
- `closeout_window`
- `open_position_present`
- `daily_loss_limit`
- `broker_truth_mismatch`
- `data_quality_guard`
- `buy_blocked_post_exit_cooldown`
- `buy_blocked_closeout_window`

## Implementation Phases

### Phase 1 - Visibility Only

Status: implemented on 2026-05-06.

- Add deterministic pre-LLM fields:
  - `pre_llm_playbook`
  - `pre_llm_market_regime`
  - `pre_llm_market_sentiment`
- Allow/normalize LLM fields:
  - `llm_requested_playbook`
  - `final_playbook`
  - `tactical_strategy`
  - `strategy_scores`
  - `rejected_strategy_reasons`
  - `candidate_watch_policy`
- Render the fields in strategist summary and trade report context.
- No behavior change yet.

Implementation notes:

- `graphs/nodes/strategist_node.py` now emits the fields on `strategist_output`.
- The same visibility fields are attached to existing `strategy_policy.market_policy`.
- The proposed watch scope is attached to existing `strategy_policy.scanner_policy.candidate_watch_policy`.
- `candidate_watch_policy.behavior_effect` is explicitly `visibility_only`, so Scanner/Monitor behavior is unchanged until Commander consumption is added.
- `libs/reporting/strategist_llm_summary.py` renders a `Strategy Detail` section from canonical strategist output when available.
- `libs/reporting/trade_report_ai.py` carries `strategy_detail` into the AI trade report compact input.
- `libs/reporting/trade_report_markdown_clean.py` renders the same fields in the trade report `전략가 출력 근거` section.

### Phase 2 - Commander Consumption

Status: implemented on 2026-05-06.

- Commander reads `strategist_output.candidate_watch_policy`.
- Commander applies safety clamps.
- Commander writes final scope to:
  - `commander_decision.entry_control`
  - `commander_decision.scanner_policy.entry_control`
  - `strategy_policy.commander_context.entry_control`
  - `strategy_policy.scanner_policy.entry_control`
  - `strategy_policy.monitor_policy.entry_control`

Implementation notes:

- `graphs/commander_runtime.py` now reads the strategist proposal from `strategist_output.candidate_watch_policy` or `strategy_policy.scanner_policy.candidate_watch_policy`.
- Commander writes the executable result as `entry_control` with `candidate_watch_policy_effect=commander_clamped_execution`.
- If no strategist proposal is present, existing baseline behavior remains unchanged.
- Hard safety clamps:
  - open position or preflight block: rank 1, runner-ups 0, cascade disabled
  - `risk_off`, defensive risk mode, stress flags, or degraded runtime: max rank 3
  - neutral/balanced: max rank 7
  - `risk_on`/offensive: max rank 10

### Phase 3 - Scanner And Monitor Enforcement

Status: implemented on 2026-05-06.

- Scanner exposes `watch_candidates` and `ranking_top_n` using final Commander scope.
- Monitor evaluates runner-up candidates only within the final Commander scope.
- Monitor cascade checks the new allowed/blocked reason lists if present.

Implementation notes:

- `graphs/nodes/scanner_node.py` now honors Commander `max_priority_rank` down to rank 1 instead of forcing at least 5 visible candidates.
- `graphs/nodes/monitor_node.py` carries final `cascade_enabled`, `cascade_allowed_reasons`, and `cascade_blocked_reasons` into the cascade plan.
- `libs/runtime/monitor_candidate_cascade.py` blocks cascade when Commander disables it or when the top-pick block reason is in the blocked reason list.

### Phase 4 - Reporting And Live Validation

Status: reporting visibility implemented on 2026-05-06; live validation pending next market run.

- AI trade report summary shows:
  - pre-LLM playbook
  - LLM requested playbook
  - final playbook
  - tactical strategy
  - strategy scores
  - rejected strategy reasons
  - proposed watch depth
  - Commander final watch depth
  - actual runner-up cascade result
- Daily patch notes should track whether defensive concentration decreases and whether watch-depth changes improve net outcomes.

Implementation notes:

- `graphs/nodes/monitor_node.py` now records top-pick reason, runner-up rank/score, fallback rank, and final selected rank in `entry_candidate_cascade`.
- `libs/reporting/trade_report_ai.py` now builds `entry_execution_visibility` from canonical strategist, Commander, and Monitor artifacts.
- Reporter compact input now exposes:
  - `entry_execution_visibility.strategy_candidate_watch_proposal`
  - `entry_execution_visibility.commander_entry_control`
  - `entry_execution_visibility.monitor_entry_candidate_cascade`
  - `commander.entry_control`
  - `monitor.entry_candidate_cascade`
- `libs/reporting/trade_report_markdown_clean.py` now renders the proposal, Commander clamp, and Monitor cascade result in both the full trade report and `ai_trade_summary.md`.

## Test Plan

Targeted tests should cover:

- strategist output normalization keeps new fields additive and bounded
- invalid strategy scores are normalized or omitted
- invalid `candidate_watch_policy.max_priority_rank` is clamped
- Commander clamps defensive/risk-off proposals to shallow watch depth
- Commander allows breakout/pullback proposals to expand only under supportive market conditions
- Monitor does not cascade on cost/risk/truth/lifecycle blockers
- Monitor may cascade on timing/fit blockers
- scanner/report artifacts show final effective watch depth
- strategist summary renders pre-LLM, LLM requested, and final playbook separately

Current validation:

- `python -m py_compile graphs/nodes/strategist_node.py libs/reporting/strategist_llm_summary.py tests/test_strategist_frame_llm_integration.py tests/test_strategist_llm_summary.py`
- `pytest tests/test_strategist_llm_summary.py tests/test_strategist_frame_llm_integration.py tests/test_m21_commander_runtime_entry.py -q`: 109 passed
- `pytest tests/test_trade_report_ai.py -q`: 114 passed
- `python -m py_compile graphs/commander_runtime.py graphs/nodes/scanner_node.py graphs/nodes/monitor_node.py libs/runtime/monitor_candidate_cascade.py tests/test_monitor_feedback_adaptive_policy.py tests/test_monitor_candidate_cascade.py`
- `pytest tests/test_m21_commander_runtime_entry.py tests/test_monitor_feedback_adaptive_policy.py tests/test_monitor_candidate_cascade.py -q`: 81 passed
- Monitor cascade regression subset:
  - `test_monitor_falls_back_to_runner_up_when_top_pick_waits`
  - `test_monitor_entry_candidate_cascade_reaches_fifth_priority_candidate`
  - `test_monitor_entry_candidate_cascade_uses_commander_priority_expansion`
  - 3 passed
- Phase 4 reporting visibility validation:
  - `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q`: 114 passed
  - `venv\Scripts\python.exe -m pytest tests\test_monitor_candidate_cascade.py tests\test_monitor_feedback_adaptive_policy.py -q`: 10 passed
  - `venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py tests\test_strategist_llm_summary.py -q`: 38 passed
  - `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`: 71 passed

Known unrelated local regression:

- Full `tests/test_monitor_exit_guard.py` currently has one failure in `test_monitor_policy_aware_gating_can_promote_breakout_near_ready_reclaim`.
- The observed blocker is `cost_adjusted_edge_not_ready`, from the existing entry cost filter path, not the candidate watch / cascade patch.

## Open Decisions

- Whether `tactical_strategy` should remain a free enum under the current four playbooks or become a first-class enum in `libs/strategies/contracts.py`.
- Whether `strategy_scores` should be fully LLM-authored at first or partially deterministic with LLM explanation.
- Whether `cost_aware_scalp` should be allowed as an overlay on both `breakout` and `pullback`, or kept as a separate tactical strategy.

Recommendation:

- Phase 1 should be visibility-only and additive.
- Phase 2 should consume only `candidate_watch_policy` after Commander clamps it.
- Strategy scoring should start as deterministic baseline plus LLM explanation, not raw LLM-only scores.
