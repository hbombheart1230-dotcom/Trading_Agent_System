# Position Refresh Contract (2026-04-19)

## Goal

This contract defines the memory used when a position is already open and the system decides to refresh the strategy frame.

This is the contract that supports long-hold re-evaluation.

## Why This Exists

Long-hold refresh is not the same as first-pass strategy selection.

At refresh time, the system already knows:

- which symbol is open
- how long it has been held
- which blockers are repeating
- which exit axis is active
- whether the current monitor policy is stagnating

If the refresh does not consume this position-specific evidence, the strategist will often return the same baseline again.

## Consumer

Primary consumer:

- the second strategist refresh during open-position reframe

Secondary consumers:

- operator diagnostics
- post-trade review

Not a direct consumer:

- first strategist pass
- scanner ranking

## Trigger

Typical trigger:

- repeated hold without resolution
- hold-duration threshold exceeded
- open-position monitor stagnation
- selective carry / closeout reframe if policy permits

## Required Content

1. position identity
- selected symbol
- entry timestamp
- position age seconds
- open quantity

2. hold progression
- hold repeat count
- selected symbol hold repeat count
- recent hold duration
- unrealized PnL summary if available

3. current monitor state
- monitor reason
- current blocking axis
- entry blockers
- transition readiness score
- active exit axis

4. policy comparison state
- prior monitor policy summary
- current monitor policy summary
- whether a new delta is required

5. selected-symbol memory excerpt
- compact symbol bias
- repeated failures
- execution risk tendency

## Minimal JSON Shape

```json
{
  "requested": true,
  "refresh_scope": "open_position_monitor_refresh",
  "selected_symbol": "005930",
  "position_context": {
    "position_age_seconds": 5400,
    "hold_repeat_count_max": 4,
    "selected_hold_repeat_count": 4,
    "active_exit_axis": "defensive_exit"
  },
  "monitor_context": {
    "monitor_reason": "repeated_hold_monitor_only",
    "current_blocking_axis": "confirmed_entry",
    "entry_blockers": ["confirmed_entry", "breakout_readiness"],
    "transition_readiness_score": 0.42
  },
  "policy_context": {
    "prior_monitor_entry_policy_summary": {
      "volume_ratio_min": 0.75,
      "max_extended_from_vwap_pct": 0.08
    },
    "current_monitor_entry_policy_summary": {
      "volume_ratio_min": 0.75,
      "max_extended_from_vwap_pct": 0.08
    },
    "requires_policy_delta": true
  },
  "symbol_memory_excerpt": {
    "prefer_playbook": "pullback",
    "avoid_playbook": "breakout",
    "repeated_failures": ["too_extended_from_vwap"],
    "spread_bps_p90": 42
  }
}
```

## LLM Usage Rule

This packet is allowed to go to LLM.

But it must go only to:

- strategist refresh

It must not create:

- scanner LLM
- monitor LLM

The owner remains strategist.

## Output Expectation

The refresh should produce:

- adjusted `monitor_entry_policy`
- `policy_adjustment`
- explicit delta fields if adjustment is required

If the refresh keeps baseline, it must say why.

## Source Reports

Preferred sources:

- current open-position state
- monitor artifact history
- deterministic trade read model
- `reports/symbols/<SYMBOL>/symbol_memory.json`

Not a source:

- long-form operator prose
- report markdown bodies

## Design Rule

If a refresh packet does not contain enough evidence to justify a possible policy delta, the refresh should either:

- explicitly keep baseline
- or not be requested

It should not pretend to adapt while returning an ungrounded generic frame.
