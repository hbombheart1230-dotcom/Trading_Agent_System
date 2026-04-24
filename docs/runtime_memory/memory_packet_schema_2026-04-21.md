# Memory Packet Schema (2026-04-21)

## Goal

This schema defines the raw memory packets that runtime will load before Commander decides how much influence each layer should have.

This document defines packet structure.

It does not define final session priority.

Session priority belongs to `commander_memory_policy`.

## Packet Set

The runtime packet set should be:

1. `daily_strategy_memory`
2. `weekly_strategy_memory`
3. `monthly_strategy_memory`
4. `symbol_memory_packet`

## Current Implementation Status

Implemented now:

- `daily_strategy_memory`
  - sourced from `strategy_memory` or `reports/performance/*`
- `weekly_strategy_memory`
  - populated from recent `reports/performance/<day>/strategy_memory.json` window aggregation
  - now includes:
    - `window`
    - `sample_quality`
    - `source_performance`
    - `source_context`
    - `failure_patterns`
    - `execution_risk`
    - `regime_stats`
    - `recommended_bias_inputs`
- `monthly_strategy_memory`
  - populated from recent `reports/performance/<day>/strategy_memory.json` window aggregation
  - now includes:
    - `window`
    - `sample_quality`
    - `source_performance`
    - `source_context`
    - `failure_patterns`
    - `execution_risk`
    - `regime_stats`
    - `recommended_bias_inputs`
- `symbol_memory_packet`
  - sourced from selected-symbol / refresh memory when available
  - now includes:
    - `trade_count`
    - `closed_trade_count`
    - `win_rate`
    - `avg_pnl_pct`
    - `avg_hold_duration_sec`
    - `data_source`
    - `unknown_fields_ratio`
    - `pattern_signal_count`
    - `evidence_strength`
    - `last_trade_date`
    - `recency_days`
    - `override_gate_reason`

Not implemented yet:

- stronger direct source-performance aggregation beyond current top-source mention inference
- richer monthly regime baseline aggregation beyond current strategy-memory rollup plus same-day supporting artifacts
- same-day reporter timing that feeds intraday strategist cycles before end-of-day metrics land

Current enrichment path:

- base packet row:
  - `reports/performance/<day>/strategy_memory.json`
- direct supporting artifacts when present:
  - `reports/metrics/metrics_<day>.json`
  - `reports/dev/analysis/reporter_analysis/reporter_analysis_<day>.json`

These supporting artifacts now enrich:

- `source_context.route_source`
- `source_context.route_selected_total`
- `source_context.strategist_mode_total`
- `source_context.alignment_totals`
- `source_context.report_focus_targets`
- `source_context.scanner_status`
- `source_context.monitor_status`
- `source_performance.*.source_selection_total`
- `source_performance.*.avg_top_score`
- `source_performance.*.avg_candidate_pool_after_filter`
- `source_performance.*.selection_status`
- `execution_risk` route/focus/status fields
- `regime_stats.*.observation_count`

Activation gate now:

- packet existence and packet activation are different
- weekly packet becomes `active=true` only when `sample_day_count >= 2`
- monthly packet becomes `active=true` only when `sample_day_count >= 3`
- weekly/monthly also require usable `sample_quality.confidence`
- below that threshold, the packet is still surfaced for observability, but Commander should not treat it as an active bias layer
- symbol override gate is also quality-aware:
  - insufficient trade history still blocks override
  - stale symbol memory still blocks override
  - poor `unknown_fields_ratio` blocks override
  - missing pattern evidence blocks override
  - `evidence_strength` is surfaced so Commander can explain why symbol memory stayed advisory-only

Implemented:

- `scanner_memory_bias` deterministic adapter
  - consumes commander-approved memory layers only
  - applies additive, capped scanner ranking deltas
  - does not let Strategist set numeric scanner deltas directly
- `monitor_memory_bias` deterministic adapter
  - consumes commander-approved memory layers only
  - currently applies conservative `entry_policy_delta`
  - does not let Strategist set numeric monitor deltas directly

## Design Rule

Packets should contain structured facts, not loose prose.

Each packet should answer:

- what happened
- how reliable the sample is
- which playbooks benefited or failed
- what deterministic bias inputs can be derived from it

## Common Packet Shape

All memory packets should share these top-level fields:

```json
{
  "schema_version": "memory_packet.v1",
  "memory_type": "daily",
  "window": {
    "label": "same_day",
    "start": "2026-04-21T00:00:00+09:00",
    "end": "2026-04-21T15:30:00+09:00"
  },
  "sample_quality": {
    "trade_count": 7,
    "filled_trade_count": 7,
    "usable": true,
    "confidence": 0.74,
    "max_age_days": 0
  },
  "playbook_stats": {},
  "failure_patterns": {},
  "execution_risk": {},
  "recommended_bias_inputs": {},
  "summary": {
    "headline": "breakout chase underperformed today",
    "bullets": [
      "extended breakout entries failed repeatedly",
      "pullback entries were more stable"
    ]
  }
}
```

## Daily Strategy Memory

Purpose:

- same-day adaptation
- today's playbook drift
- today's repeated blockers

Required sections:

- `playbook_stats`
- `failure_patterns`
- `session_regime_observation`
- `recommended_bias_inputs`

Example:

```json
{
  "memory_type": "daily",
  "playbook_stats": {
    "breakout": {"count": 4, "win_rate": 0.0, "avg_return_pct": -0.011},
    "pullback": {"count": 3, "win_rate": 0.67, "avg_return_pct": 0.004}
  },
  "failure_patterns": {
    "dominant_blockers": ["too_extended_from_vwap", "volume_insufficient"],
    "repeat_stopouts": 3
  },
  "recommended_bias_inputs": {
    "scanner": {
      "extended_chase_penalty": 0.18
    },
    "monitor": {
      "volume_ratio_min_delta": 0.03,
      "max_extended_from_vwap_pct_delta": -0.01
    }
  }
}
```

## Weekly Strategy Memory

Purpose:

- medium-horizon pattern persistence
- recent source-quality drift
- stable playbook preference

Required sections:

- `source_performance`
- `playbook_stats`
- `regime_fit`
- `recommended_bias_inputs`

Example:

```json
{
  "memory_type": "weekly",
  "source_performance": {
    "top_value": {"trade_count": 11, "avg_return_pct": 0.003},
    "top_change_rate": {"trade_count": 8, "avg_return_pct": -0.007}
  },
  "recommended_bias_inputs": {
    "scanner": {
      "source_weight_delta": {
        "top_value": 0.10,
        "top_change_rate": -0.20
      }
    }
  }
}
```

## Monthly Strategy Memory

Purpose:

- baseline doctrine
- long-horizon playbook stability
- regime baseline

Required sections:

- `baseline_playbook_preference`
- `regime_stats`
- `risk_posture_baseline`

Monthly memory should influence posture more than short-lived symbol exceptions.

## Symbol Memory Packet

Purpose:

- deterministic symbol prior
- selected-symbol refresh support
- hold/exit risk hints for the selected symbol

Required sections:

- `trade_stats`
- `playbook_stats`
- `execution_risk`
- `monitor_patterns`
- `bias_recommendation`

Example:

```json
{
  "memory_type": "symbol",
  "symbol": "005930",
  "trade_stats": {
    "trade_count": 14,
    "win_rate": 0.36,
    "avg_return_pct": -0.004
  },
  "playbook_stats": {
    "breakout": {
      "count": 9,
      "win_rate": 0.22,
      "dominant_failures": ["too_extended_from_vwap", "volume_insufficient"]
    },
    "pullback": {
      "count": 5,
      "win_rate": 0.60
    }
  },
  "bias_recommendation": {
    "prefer_playbook": "pullback",
    "avoid_playbook": "breakout",
    "scanner_penalty": 0.08
  }
}
```

## Packet Usage Rule

Raw packets do not directly change runtime thresholds.

Instead:

1. runtime loads packets
2. Commander approves layer usage
3. deterministic adapters convert packet facts into bias deltas

That split is mandatory.

## Planned Module Ownership

To keep modules thin, implementation should split like this:

- `libs/runtime/memory_packet_loader.py`
- `libs/runtime/daily_strategy_memory_packet.py`
- `libs/runtime/weekly_strategy_memory_packet.py`
- `libs/runtime/monthly_strategy_memory_packet.py`
- `libs/runtime/symbol_memory_packet.py`

No single module should own every memory packet shape.
