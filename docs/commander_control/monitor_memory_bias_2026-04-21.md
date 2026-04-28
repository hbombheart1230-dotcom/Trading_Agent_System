# Monitor Memory Bias (2026-04-21)

## Goal

`monitor_memory_bias` is the deterministic adapter output that converts approved memory packets into monitor-side policy deltas.

It should influence:

- entry thresholds
- hold posture
- exit posture

It must not become a hidden second strategist.

## Current Status

Initial implementation is in place.

Current runtime now exposes and applies:

- `commander_memory_policy`
- raw `memory_packets`
- deterministic `monitor_memory_bias`

Current implementation scope:

- `entry_policy_delta`
- first-pass `hold_policy_delta`
- first-pass `exit_policy_delta`
- conservative tightening only
- Commander `policy_signals` now affect entry tightening strength:
  - `preferred_risk_posture`
  - `system_health`
  - `monitor_status`
  - `monitor_only_ratio`
  - `report_focus_targets`
- Commander `policy_signals` now also affect hold/exit tightening strength using the same posture surface
- symbol-memory `evidence_strength` and `recency_days` now damp or block symbol-derived hold/exit tightening

Applied deltas are surfaced in:

- canonical monitor artifact
- strategist visibility
- commander decision surface

## Inputs

Required inputs:

- `commander_memory_policy`
- `daily_strategy_memory`
- `weekly_strategy_memory`
- `monthly_strategy_memory`
- `symbol_memory_packet`
- current runtime posture
- selected symbol context

## Output Shape

```json
{
  "monitor_memory_bias": {
    "active_layers": ["daily", "weekly", "symbol"],
    "entry_policy_delta": {
      "volume_ratio_min": 0.03,
      "max_extended_from_vwap_pct": -0.01,
      "breakout_buffer_pct": 0.002
    },
    "hold_policy_delta": {
      "stagnation_patience_sec": -120,
      "reclaim_grace_sec": -60
    },
    "exit_policy_delta": {
      "peak_drawdown_mode": "always_on",
      "vwap_break_requires_profit": false,
      "intraday_low_break_pct": -0.001
    },
    "risk_posture": "defensive",
    "reason": [
      "daily repeated stopouts justify tighter entry extension control",
      "symbol memory shows weak breakout follow-through",
      "weekly source quality still favors pullback behavior"
    ]
  }
}
```

## Allowed Adjustment Types

### 1. Entry policy delta

Examples:

- `volume_ratio_min`
- `max_extended_from_vwap_pct`
- `breakout_buffer_pct`
- `confidence_threshold`

### 2. Hold policy delta

Examples:

- reclaim grace
- stagnation patience
- refresh escalation timing

### 3. Exit policy delta

Examples:

- `peak_drawdown_mode`
- `vwap_break_requires_profit`
- `intraday_low_break_pct`
- `hard_stop_pct`

## Hard Rules

### Rule 1

Monitor bias must be deterministic.

### Rule 2

`symbol_memory_packet` may tighten policy only when Commander gates allow it.

### Rule 3

Monthly memory should provide baseline posture, not noisy intraday micro-adjustment.

### Rule 4

Daily memory may tighten policy aggressively only when same-day sample quality is usable.

### Rule 5

Commander posture signals may add conservative tightening on top of memory-derived deltas.

Examples:

- defensive / RED / high monitor-only pressure:
  - tighter `max_extended_from_vwap_pct`
  - slightly larger `breakout_buffer_pct`
- `monitor_status = overtrading_risk`:
  - larger `breakout_buffer_pct`
  - larger `volume_ratio_min`
- `report_focus_targets` includes `exit_quality` or `guard_blocks`:
  - extra entry conservatism is allowed
  - extra exit conservatism is also allowed

### Rule 6

Approved `symbol_memory_packet` should not always apply full-strength symbol tightening.

Current symbol-side scaling inputs:

- `evidence_strength`
- `recency_days`

Current effect:

- strong and fresh symbol memory keeps full symbol-derived entry deltas
- moderate or aging symbol memory dampens symbol-derived entry deltas
- stale symbol memory blocks symbol-derived entry deltas even if symbol override is forced upstream
- the same damping/blocking now also applies to symbol-derived hold/exit deltas

## Required Visibility

The runtime should surface:

- which layers were active
- which deltas were applied
- which reasons justified the deltas

That should appear in:

- canonical monitor artifact
- trade report memory surface
- future commander memory trace

Current live-validation targets:

- top-level `monitor_memory_bias_applied`
- top-level `monitor_memory_bias_hold_applied`
- top-level `monitor_memory_bias_exit_applied`
- top-level `commander_memory_application_trace`
- `exit_policy_guard_adjustments` entries for:
  - `commander_memory_bias_hold:*`
  - `commander_memory_bias_exit:*`

`commander_memory_application_trace` is the preferred inspection field when
checking whether Commander memory actually affected monitor behavior. It records:

- capture/enabled/applied state
- skipped reason when not applied
- entry/hold/exit applied flags
- entry/hold/exit delta keys
- entry/hold/exit concrete deltas
- effective policy source and source chain
- risk posture and raw reasons

## Anti-Pattern

Do not let monitor read raw memory prose and self-adjust through ad hoc interpretation.

Monitor should only consume:

- approved `monitor_memory_bias`
- approved policy delta

## Planned Module Ownership

Keep this split thin:

- `libs/runtime/monitor_memory_bias.py`
- `libs/runtime/monitor_memory_bias_rules.py`
- `libs/runtime/monitor_memory_bias_reasons.py`

Current runtime integration:

- `graphs/commander_runtime.py`
- `graphs/nodes/strategist_node.py`
- `graphs/nodes/monitor_node.py`
