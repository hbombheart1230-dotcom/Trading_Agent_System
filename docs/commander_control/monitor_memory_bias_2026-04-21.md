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

- `entry_policy_delta` only
- conservative tightening only
- no `hold_policy_delta` or `exit_policy_delta` application yet

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

## Required Visibility

The runtime should surface:

- which layers were active
- which deltas were applied
- which reasons justified the deltas

That should appear in:

- canonical monitor artifact
- trade report memory surface
- future commander memory trace

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
