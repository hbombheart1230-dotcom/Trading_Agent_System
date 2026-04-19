# Symbol Memory Redefinition Plan (2026-04-19)

## Goal

Redefine `reports/symbols` from a vague operator-facing report into a real symbol-memory source.

The new purpose is:

1. feed scanner deterministic symbol priors
2. feed selected-symbol strategist refresh
3. feed long-hold position refresh with symbol-specific evidence

This is not a new LLM lane.
This is a better memory surface.

## Current State

Current implementation:

- `libs/reporting/symbol_trade_report.py`
- canonical output path:
  - `reports/symbols/<SYMBOL>/symbol_trade_report.json`
  - `reports/symbols/<SYMBOL>/symbol_trade_report.md`
  - `reports/symbols/<SYMBOL>/trade_history.json`
  - `reports/symbols/<SYMBOL>/daily_index.json`
  - `reports/symbols/<SYMBOL>/latest_snapshot.json`

Current payload already contains useful raw material:

- trade count
- completed trade count
- win / loss count
- average return
- average hold seconds
- recent playbooks
- recent entry / exit / wait reasons
- wait reason distribution
- recent trade headlines
- recent operator viewpoints
- successful / failed entry patterns
- common monitor failures
- recent entry / exit pattern types
- recent improvement tags
- recent review flags
- full history index

This is a usable source, but not yet a scanner-ready or refresh-ready memory packet.

## Why Redefinition Is Needed

Current `symbol_trade_report.v1` is mostly a human-readable historical report.

Problems:

1. scanner cannot consume it deterministically without extra shaping
2. playbook-specific bias is not explicit enough
3. execution-risk fields are missing or weak
4. refresh-oriented fields are not separated from operator prose

So the issue is not “symbols report is useless”.
The issue is “symbols report is not yet shaped as runtime memory”.

## Target Split

Keep the existing symbol history outputs as source material, but add a compact runtime packet.

Recommended target outputs:

- `reports/symbols/<SYMBOL>/symbol_trade_report.json`
  - keep as rich history source
- `reports/symbols/<SYMBOL>/symbol_memory.json`
  - new compact runtime packet
- `reports/symbols/<SYMBOL>/latest_snapshot.json`
  - keep for fast inspection

Do not add a parallel mirror path right now.

For now, `reports/symbols/<SYMBOL>/symbol_memory.json` is the canonical symbol-memory packet.

## Consumer Split

### Scanner

Scanner should read deterministic fields only.

Allowed scanner usage:

- `scanner_penalty`
- `scanner_bonus`
- `prefer_playbook`
- `avoid_playbook`
- `risk_cap`
- execution risk penalty
- repeated blocker penalty

Scanner should not read long prose or history rows directly.

### Strategist Refresh

Selected-symbol or long-hold refresh may read a compact excerpt.

Allowed strategist-refresh usage:

- dominant failures
- playbook fit / avoid hints
- execution risk tendency
- hold refresh effectiveness
- repeated blockers

This stays inside the strategist refresh lane.

### Monitor

Monitor should not read raw symbol history directly.
It should inherit updated policy and small deterministic flags only.

## Field Mapping

## Existing Fields To Reuse As-Is

From `symbol_trade_report.json.summary`:

- `trade_count`
- `completed_trade_count`
- `win_count`
- `loss_count`
- `avg_return_pct`
- `avg_hold_seconds`
- `recent_playbooks`
- `recent_entry_reasons`
- `recent_exit_reasons`
- `recent_wait_reasons`
- `wait_reason_distribution`

From `symbol_trade_report.json.pattern_insights`:

- `successful_entry_patterns`
- `failed_entry_patterns`
- `common_monitor_failures`
- `recent_entry_pattern_types`
- `recent_exit_pattern_types`
- `recent_improvement_tags`
- `recent_review_flags`

From `latest_snapshot.json`:

- `last_trade_id`
- `last_status`
- `trade_origin`
- `lifecycle_completeness`
- `evidence_recovery_used`

## Existing Fields To Derive

These should be derived from current history rows:

1. `win_rate`
- `win_count / completed_trade_count`

2. `playbook_stats`
- count by playbook
- win rate by playbook
- average return by playbook

3. `entry_pattern_stats`
- frequency and success rate by entry pattern

4. `exit_pattern_stats`
- frequency by exit pattern

5. `dominant_failure_patterns`
- from failed entry patterns
- common monitor failures
- recurring exit causes

## New Fields To Add

These are needed to make symbol memory useful in runtime decisions.

### Required for scanner deterministic priors

- `bias_recommendation.scanner_penalty`
- `bias_recommendation.scanner_bonus`
- `bias_recommendation.prefer_playbook`
- `bias_recommendation.avoid_playbook`
- `bias_recommendation.risk_cap`

### Required for execution risk

- `execution_risk.spread_bps_p50`
- `execution_risk.spread_bps_p90`
- `execution_risk.slippage_bps_p50`
- `execution_risk.execution_risk_level`

### Required for hold-refresh quality

- `monitor_patterns.hold_refresh_count`
- `monitor_patterns.hold_refresh_effective_count`
- `monitor_patterns.hold_refresh_effective_rate`

### Required for repeated blocker shaping

- `monitor_patterns.repeated_blockers`
- `monitor_patterns.dominant_wait_reason`
- `monitor_patterns.dominant_exit_failure_axis`

## Target `symbol_memory.json` Shape

```json
{
  "schema_version": "symbol_memory.v1",
  "symbol": "005930",
  "window_label": "rolling_recent",
  "trade_stats": {
    "trade_count": 14,
    "completed_trade_count": 11,
    "win_rate": 0.36,
    "avg_return_pct": -0.40,
    "avg_hold_seconds": 540.0
  },
  "playbook_stats": {
    "breakout": {
      "count": 9,
      "win_rate": 0.22,
      "avg_return_pct": -0.73
    },
    "pullback": {
      "count": 5,
      "win_rate": 0.60,
      "avg_return_pct": 0.48
    }
  },
  "pattern_stats": {
    "successful_entry_patterns": ["pullback", "reclaim"],
    "failed_entry_patterns": ["breakout"],
    "common_monitor_failures": ["confirmed_entry", "breakout_readiness"]
  },
  "execution_risk": {
    "spread_bps_p50": 18,
    "spread_bps_p90": 42,
    "slippage_bps_p50": 11,
    "execution_risk_level": "medium"
  },
  "monitor_patterns": {
    "repeated_blockers": ["confirmed_entry", "breakout_readiness"],
    "dominant_wait_reason": "volume_confirmation_missing",
    "hold_refresh_count": 5,
    "hold_refresh_effective_count": 1,
    "hold_refresh_effective_rate": 0.20
  },
  "bias_recommendation": {
    "scanner_penalty": 0.08,
    "scanner_bonus": 0.00,
    "prefer_playbook": "pullback",
    "avoid_playbook": "breakout",
    "risk_cap": "conservative"
  },
  "latest_snapshot": {
    "last_trade_id": "TRD_20260417_005930_01",
    "last_status": "open"
  }
}
```

## Scanner Consumption Rule

Scanner should consume only these:

- `bias_recommendation.*`
- `execution_risk.*`
- `monitor_patterns.repeated_blockers`
- playbook-specific stats needed for rank penalty/bonus

Scanner should not read:

- headlines
- operator viewpoints
- long-form markdown
- full history rows

## Refresh Consumption Rule

Strategist refresh may consume:

- `playbook_stats`
- `pattern_stats`
- `execution_risk`
- `monitor_patterns`
- `bias_recommendation`
- `latest_snapshot`

But only as a compact excerpt inside the refresh packet.

## Migration Sequence

1. keep current `symbol_trade_report.json` generation intact
2. add `symbol_memory.json` beside it
3. wire scanner to deterministic fields only
4. wire selected-symbol / long-hold strategist refresh to compact excerpt only
5. later decide whether operator-facing symbol markdown is still worth default generation

## Immediate Implementation Target

The next implementation slice should do only this:

1. add `symbol_memory.json`
2. populate deterministic stats and bias fields
3. do not yet wire scanner or strategist refresh

That keeps the contract stable before consumer changes begin.
