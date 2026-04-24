# Commander Memory Authority

## Conclusion

Memory-layer arbitration is Commander-owned.

This is not an optional preference. It is part of the system identity.

Strategist may interpret memory and propose changes, but Strategist does not own:

- which memory layers are active today
- which layer has priority
- whether symbol-memory override is allowed
- whether memory confidence is high enough to influence runtime policy

Those decisions belong to `commander`.

## Ownership Split

### Commander

Commander owns:

- active memory layers
- layer priority order
- symbol-memory override gate
- confidence and recency gates
- support-context readiness gates
- approval of scanner-memory bias
- approval of monitor-memory bias

Support-context readiness means Commander may use:

- `route_source`
- `report_focus_targets`
- `scanner_status`
- `monitor_status`
- regime observation counts

to decide whether a weekly/monthly layer is active enough to influence runtime,
even when the raw packet exists.

Commander should emit a single policy surface such as:

```json
{
  "commander_memory_policy": {
    "active_layers": ["daily", "weekly", "symbol"],
    "priority_order": ["daily", "symbol", "weekly", "monthly"],
    "symbol_memory_override_enabled": true,
    "symbol_memory_min_trade_count": 5,
    "symbol_memory_max_age_days": 20,
    "scanner_bias_enabled": true,
    "monitor_bias_enabled": true,
    "reason": [
      "daily memory dominates current session behavior",
      "symbol memory is reliable enough for the selected ticker"
    ]
  }
}
```

### Strategist

Strategist owns:

- interpreting approved memory context
- choosing a playbook inside the approved envelope
- proposing memory emphasis changes
- explaining why a change should be accepted

Strategist may emit a proposal surface such as:

```json
{
  "memory_override_proposal": {
    "prefer_layers": ["daily", "symbol"],
    "avoid_layers": ["monthly"],
    "reason": "today's repeated intraday failures are more relevant than monthly baseline"
  }
}
```

Strategist does not directly mutate scanner scores or monitor thresholds.

### Deterministic Adapters

Runtime adapters own the actual numeric adjustments:

- `scanner_memory_bias`
- `monitor_memory_bias`

Those adapters must be deterministic.

The LLM may suggest direction. The runtime adapter applies the approved deltas.

## Why Commander Must Own This

### 1. Session consistency

If Strategist owns memory arbitration, session posture can drift away from:

- scanner ranking
- monitor entry thresholds
- monitor exit thresholds
- closeout behavior

Commander is the only layer that can keep those aligned.

### 2. Safety

Symbol memory is dangerous without gating.

It must be bounded by:

- minimum sample count
- maximum age
- regime fit
- confidence threshold

That is an approval problem, not a narrative problem.

### 3. Clear responsibility

The clean split is:

- Commander: approve and control
- Strategist: interpret and propose
- Scanner/Monitor: apply deterministically

## Immediate Design Direction

## Current Implementation Status

Implemented now:

- `commander_decision.memory_packets`
- `commander_decision.commander_memory_policy`
- `strategist` context surface for both fields
- strategist artifact visibility for both fields

Current mode:

- additive only
- `application_mode = surface_only`
- no scanner score delta applied yet
- no monitor threshold delta applied yet

Next implementation step:

- build deterministic adapters
  - `scanner_memory_bias`
  - `monitor_memory_bias`

The next stable surfaces should be:

1. `commander_memory_policy`
2. `daily_strategy_memory`
3. `weekly_strategy_memory`
4. `monthly_strategy_memory`
5. `symbol_memory_packet`
6. `scanner_memory_bias`
7. `monitor_memory_bias`

The runtime should consume them in this order:

1. load memory packets
2. Commander arbitrates layer priority and gates
3. deterministic adapters produce scanner and monitor bias
4. Strategist reads approved memory policy and packet summaries
5. Scanner and Monitor apply the resulting bias

## Explicit Anti-Pattern

Do not let Strategist directly decide:

- scanner source-weight deltas
- scanner symbol penalties
- monitor threshold deltas
- monitor exit-policy deltas

That would make the LLM the hidden runtime controller.

Commander must stay in control.
