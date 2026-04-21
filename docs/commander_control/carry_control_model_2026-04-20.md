# Carry Control Model

## Goal

Model overnight and stale carry as Commander-owned state, not as a loose
collection of monitor-side heuristics.

The objective is:

- treat same-session positions differently from overnight positions
- treat overnight positions differently from multi-session stale positions
- make session-open recovery quality part of Commander control

## Problem Statement

Current runtime already has:

- `session_bias = position_management` when open positions exist
- repeated-hold strategist refresh
- monitor-side overnight carry approval at end of day

Current remaining weakness:

- next-session carry handling still uses a proxy-style recovery model
- weak overnight openings are not yet judged with a direct gap/opening-range model
- scanner narrowing is still not driven directly by carry-risk bias

## Core State Model

### `carry_state`

Commander should classify each open position into exactly one state:

- `same_session`
- `overnight_open`
- `multi_session_stale`

Interpretation:

- `same_session`
  - opened today
  - normal intraday hold/exit logic dominates
- `overnight_open`
  - opened before today
  - session-open recovery must be evaluated explicitly
- `multi_session_stale`
  - position survived more than one session or shows repeated hold deterioration
  - carry justification should be presumed weak unless evidence says otherwise

### `carry_risk_bias`

Commander should compute a session-level carry posture:

- `normal`
- `elevated`
- `urgent_exit_review`

Interpretation:

- `normal`
  - open positions do not materially distort new-session routing
- `elevated`
  - existing positions should narrow scanner scope and tighten exit posture
- `urgent_exit_review`
  - carry-risk handling must dominate over new candidate exploration

### `session_open_recovery_assessment`

Commander should assess whether an overnight position actually recovers after the
new session opens.

Suggested fields:

- `evaluated`
- `minutes_from_open`
- `gap_direction`
- `gap_pct`
- `vwap_reclaim_ok`
- `opening_recovery_ok`
- `volume_recovery_ok`
- `recovery_quality`
- `recovery_failure_axes`

Suggested `recovery_quality` values:

- `strong`
- `mixed`
- `weak`
- `failed`

## Commander Interpretation Rules

### Rule 1

If `carry_state = overnight_open`, Commander must evaluate session-open recovery.

### Rule 2

If `carry_state = overnight_open` and `recovery_quality = failed`, Commander
must not treat the position as ordinary intraday hold.

### Rule 3

If `carry_state = multi_session_stale`, Commander should default to
`carry_risk_bias = elevated` or `urgent_exit_review` unless new evidence is
clearly supportive.

### Rule 4

Commander should not blindly force exit just because a position is overnight.

Instead, Commander should combine:

- carry state
- loss state
- repeated hold state
- session-open recovery quality
- active exit axis

## Handoff Consequences

### Strategist

Commander should pass carry context into strategist refresh so strategist can
adjust:

- exit posture
- monitor focus
- carry bias

### Monitor

Commander should still keep `monitor_entry_policy` as the direct execution
contract, but monitor posture must reflect carry-risk-biased control.

### Scanner

Commander should narrow or deprioritize scanner exploration when carry-risk is
elevated.

## Recommended First Implementation

### Phase 1

Add Commander-side derived fields:

- `carry_state`
- `carry_risk_bias`
- `session_open_recovery_assessment`

### Phase 2

Include those fields in:

- `commander_decision`
- `strategist_refresh_context`
- `open_position_refresh_context`

Current status:

- implemented
- current assessment is intentionally conservative and proxy-based
- session-open recovery currently relies on existing monitor-side signals such as:
  - `entry_state.current_blocking_axis`
  - `reclaim_gate_ok`
  - `volume_ok`
  - `monitor_reason`
  - `active_exit_axis`
  - `effective_loss_ratio`
- no direct open-gap percentage model is wired into Commander yet

### Phase 3

Use these fields to tighten session posture for:

- weak overnight openings
- repeated-hold stale positions
- mismatch between active exit axis and open recovery quality

Current status:

- partially implemented
- Commander now:
  - can force monitor-only routing for `urgent_exit_review`
  - changes `scanner_mission`, `monitor_mission`, `flow_instruction`, and `command_intent`
    toward carry-risk-first handling
- Commander now injects carry-scoped exit overrides into applied monitor policy:
  - `vwap_break_requires_profit`
  - `hard_stop_pct`
  - `intraday_low_break_pct`
  - `trend_strength_floor`
  - `peak_drawdown_mode` for failed session-open recovery
- preopen can now request `preopen_carry_risk_review` before new entries
- not implemented yet:
  - scanner ranking/scoring adjustments driven by carry state
  - stronger direct gap/opening-range recovery model
  - live-effectiveness validation on fresh runtime artifacts
