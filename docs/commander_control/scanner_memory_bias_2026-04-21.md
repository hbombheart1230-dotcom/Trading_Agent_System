# Scanner Memory Bias (2026-04-21)

## Goal

`scanner_memory_bias` is the deterministic adapter output that converts approved memory packets into scanner-side ranking adjustments.

The adapter does not decide whether a memory layer is active.

Commander decides that first.

## Current Status

Initial implementation is in place.

Current runtime now does all of the following:

- Commander builds `scanner_memory_bias`
- Scanner applies additive deterministic score deltas
- Scanner artifact surfaces:
  - `scanner_memory_bias_applied`
  - `scanner_memory_bias`
  - `scanner_memory_bias_summary`
  - `candidate_memory_bias_adjustments`
  - `selection_reason_with_bias`
  - `commander_memory_application_trace`

The application trace is the preferred inspection field when checking whether
Commander memory actually affected scanner ranking. It records:

- capture/enabled/applied state
- skipped reason when not applied
- selected symbol
- selected candidate sources
- matching source delta keys
- selected source and symbol deltas
- selected bias adjustments

Current limitations:

- adjustment size is intentionally capped and conservative
- only a narrow rule set is active
- `monitor_memory_bias` remains separate and is now implemented in its initial entry-policy-only form
- Commander `policy_signals` now affect bias strength:
  - `preferred_risk_posture`
  - `system_health`
  - `scanner_status`
  - `monitor_only_ratio`
  - `report_focus_targets`

## Inputs

Required inputs:

- `commander_memory_policy`
- `daily_strategy_memory`
- `weekly_strategy_memory`
- `monthly_strategy_memory`
- `symbol_memory_packet`
- candidate snapshot

## Output Shape

```json
{
  "scanner_memory_bias": {
    "active_layers": ["daily", "symbol"],
    "source_weight_delta": {
      "top_value": 0.10,
      "top_change_rate": -0.20
    },
    "feature_bias": {
      "extended_chase_penalty": -0.18,
      "vwap_reclaim_bonus": 0.06,
      "repeat_symbol_penalty": -0.10
    },
    "symbol_adjustments": {
      "005930": {"penalty": -0.08, "reason": "breakout quality weak"},
      "000660": {"bonus": 0.05, "reason": "pullback quality stable"}
    },
    "confidence_caps": {
      "max_confidence": 0.88
    },
    "reason": [
      "daily extended entries underperformed",
      "weekly top_change_rate quality degraded",
      "symbol memory discourages breakout for 005930"
    ]
  }
}
```

## Allowed Adjustment Types

### 1. Source weight delta

Applies to:

- `top_value`
- `top_volume`
- `top_change_rate`
- future scanner sources

### 2. Feature bias

Applies to:

- extended entry penalty
- reclaim bonus
- weak-volume penalty
- repeat-symbol penalty

### 3. Symbol adjustment

Applies only when symbol-memory gates pass:

- minimum trade count
- recency threshold
- confidence threshold

### 4. Confidence cap

Used when memory says ranking confidence should be bounded even if raw score is high.

## Hard Rules

### Rule 1

If Commander disables a layer, the adapter must ignore that layer completely.

### Rule 2

`symbol_memory_packet` may not influence scanner unless Commander explicitly enables symbol override.

### Rule 3

The adapter may not call an LLM.

### Rule 4

Each applied delta must preserve a machine-readable reason.

### Rule 5

Commander posture signals may scale bias strength, but only conservatively.

Examples:

- defensive / RED / scanner-fit pressure:
  - more positive `top_value`
  - more negative `top_change_rate`
- scanner status weak or misaligned:
  - stronger overextension penalty
- guard-block focus:
  - stronger volume-confirmation preference

### Rule 6

Approved `symbol_memory_packet` does not imply full-strength symbol bias.

Current symbol-side scaling inputs:

- `evidence_strength`
- `recency_days`

Current effect:

- strong and fresh symbol memory keeps full symbol delta
- moderate or aging symbol memory dampens symbol delta
- stale symbol memory blocks symbol delta even if a caller misflags symbol override

## Anti-Pattern

Do not let Strategist directly say:

- add 0.13 to candidate X
- subtract 0.09 from source Y

Strategist may propose a direction.

The deterministic adapter computes the actual delta.

## Planned Module Ownership

Keep this thin:

- `libs/runtime/scanner_memory_bias.py`
- `libs/runtime/scanner_memory_bias_rules.py`
- `libs/runtime/scanner_memory_bias_reasons.py`

Do not collapse all scanner memory logic into one large module.
