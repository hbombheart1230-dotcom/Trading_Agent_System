# Commander Entry Participation Control

Date: 2026-04-27

## Purpose

This document defines Commander-owned entry participation control.

The problem this addresses:

- Scanner can keep finding reasonable candidates.
- Strategist can keep providing a usable frame.
- Monitor can still reject every candidate for the same repeated reason.
- If market context is supportive, the system should broaden participation instead of repeatedly checking the same narrow pool.
- If market context is defensive, fewer trades should be an explicit Commander decision, not an accidental side effect of hard-coded monitor guards.

## Authority Boundary

Commander controls participation posture.

Commander does not:

- select the final stock
- override scanner ranking directly
- force monitor to emit a BUY
- execute orders
- lower or bypass hard safety guards unconditionally

Scanner still ranks candidates.

Monitor still validates entry quality.

Decision and executor still own approval and execution.

## Runtime Contract

Commander emits `commander_decision.entry_control`.

Canonical shape:

```json
{
  "schema_version": "commander_entry_control.v1",
  "source": "commander_decision",
  "mode": "expand_when_market_ok",
  "decision": "expand_candidate_pool_and_dynamic_entry_band",
  "market_regime": "neutral",
  "risk_mode": "balanced",
  "market_supportive": true,
  "dominant_blocker": "too_extended_from_vwap",
  "failure_streak": 5,
  "near_ready_flag": true,
  "avg_distance_to_ready": 0.82,
  "max_priority_rank": 10,
  "max_runner_ups": 9,
  "allow_dynamic_entry_band": true,
  "adaptive_max_extended_from_vwap_pct": 0.1,
  "max_extended_from_vwap_pct_cap": 0.1,
  "scan_aggressiveness_floor": 0.1,
  "reason": "market_supportive_repeated_blocker:too_extended_from_vwap:streak=5"
}
```

## Modes

`baseline`

Default mode. No participation expansion is required.

`expand_when_market_ok`

Market context is supportive and an expandable monitor blocker has repeated. Commander broadens candidate participation by increasing scanner scan aggressiveness and extending monitor runner-up review beyond the default Top-5.

`preserve_defensive_no_trade_ok`

The same blocker repeated, but market or risk mode is not supportive. Commander explicitly accepts fewer entries instead of widening participation.

`preserve_guardrail_no_trade_ok`

The dominant blocker is not expandable. Commander keeps the guardrail intact.

`blocked_no_entry_expansion`

Preflight or runtime status is blocked. No entry expansion is allowed.

`position_management_no_entry_expansion`

An open position exists. Commander keeps focus on position management rather than new entries.

`observe_repeated_blocker`

A repeated blocker is observed, but conditions are insufficient for expansion.

## Decision Rules

Commander treats market as supportive only when:

- `risk_mode` is `balanced` or `offensive`
- `market_regime` is `neutral` or `risk_on`
- there are no macro stress flags
- runtime resilience is not degraded
- portfolio preflight is not blocked
- no open position is active

Expandable blockers currently include:

- `too_extended_from_vwap`
- `still_overextended_after_pullback`
- `breakout_not_ready`
- `below_vwap_reclaim_not_ready`
- `pullback_below_vwap_reclaim_not_ready`
- `reclaim_not_ready`
- `volume_confirmation_missing`
- `volume_insufficient`
- `volume_missing`
- `entry_wait`
- `wait_for_confirmation`

When repeated blocker count is at least 3 and market is supportive:

- `mode=expand_when_market_ok`
- `scan_aggressiveness_floor=0.05`
- `max_priority_rank=8`
- `max_runner_ups=7`

When repeated blocker count is at least 5:

- `scan_aggressiveness_floor=0.10`
- `max_priority_rank=10`
- `max_runner_ups=9`

For VWAP overextension blockers only:

- Commander may set `allow_dynamic_entry_band=true`
- target band is `0.08` first
- target band can reach `0.10` when the streak is at least 5 and the setup is near-ready
- cap remains bounded by `max_extended_from_vwap_pct_cap=0.10`

This is widening a Commander-approved entry participation band. It is not a forced buy.

## Handoff Path

`graphs/commander_runtime.py`

- `_build_commander_decision` computes `monitor_feedback`.
- `_build_commander_entry_control` derives participation mode.
- `scanner_policy` receives `max_priority_rank`, `max_runner_ups`, `scan_aggressiveness`, and nested `entry_control`.

`_attach_commander_applied_policy`

- propagates `entry_control` into:
  - `commander_applied_policy`
  - `strategy_policy.commander_context`
  - `strategy_policy.monitor_policy`
  - `strategy_policy.scanner_policy`
  - `strategist_output.commander_entry_control`

`graphs/nodes/monitor_node.py`

- resolves Commander entry control from commander context, monitor policy, applied policy, or commander decision.
- injects the control into monitor entry policy input.
- configures `entry_candidate_cascade.max_priority_rank`.

`libs/runtime/intraday_monitor_signals.py`

- applies `commander_entry_control:dynamic_entry_band` only when `allow_dynamic_entry_band=true`.
- keeps defensive playbook tightening intact when Commander did not authorize expansion.

## Observability

Expected runtime surfaces:

- `commander_decision.entry_control`
- `commander_decision.scanner_policy.entry_control`
- `commander_decision.policy_adjustment_trace`
- `commander_decision.observations.entry_control_mode`
- `commander_decision.source_refs.entry_control`
- `strategy_policy.commander_context.entry_control`
- `strategy_policy.monitor_policy.entry_control`
- `strategy_policy.scanner_policy.entry_control`
- `monitor.commander_entry_control`
- `monitor_output.entry_candidate_cascade.max_priority_rank`
- `monitor_output.entry_candidate_cascade.control_mode`

Important artifact note:

- Scanner display surfaces may still show Top-5 watch candidates.
- Monitor can still review more than Top-5 through `ranked_candidates` when Commander expands `max_priority_rank`.

## Safety Invariants

- No open position expansion: if a position exists, entry participation stays narrow.
- No blocked expansion: preflight or runtime blocked states cannot widen participation.
- No risk-off widening: defensive market conditions explicitly preserve low trade count.
- No forced BUY: monitor confirmation, cooldowns, closeout guards, and decision approval remain authoritative.
- Dynamic VWAP widening is bounded and only active when Commander explicitly emits `allow_dynamic_entry_band=true`.

## Tests

Covered by:

- `tests/test_monitor_feedback_adaptive_policy.py`
- `tests/test_intraday_monitor_signals.py::test_commander_entry_control_widens_defensive_vwap_band_only_when_allowed`
- `tests/test_monitor_exit_guard.py::test_monitor_entry_candidate_cascade_uses_commander_priority_expansion`
- `tests/test_m21_commander_runtime_entry.py::test_attach_commander_applied_policy_recomputes_memory_bias_instead_of_using_stale_commander_decision`

Validated command set on 2026-04-27:

- `venv\Scripts\python.exe -m pytest tests/test_m21_commander_runtime_entry.py -q`
- `venv\Scripts\python.exe -m pytest tests/test_intraday_monitor_signals.py -q`
- `venv\Scripts\python.exe -m pytest tests/test_scanner_monitor_compatibility.py -q`

## Live Validation Checklist

Next live session should verify:

- `entry_control.mode=expand_when_market_ok` appears after repeated expandable blockers in supportive market.
- `monitor_output.entry_candidate_cascade.max_priority_rank` exceeds 5 when Commander expands participation.
- dynamic VWAP band appears in effective policy adjustments only when Commander authorizes it.
- no expansion occurs during `post_exit_cooldown`, closeout window, preflight blocked state, or open-position management.
- no-trade traces distinguish expected defensive inactivity from unexpected repeated candidate rejection.
