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
  - placeholder packet, not populated yet
- `monthly_strategy_memory`
  - placeholder packet, not populated yet
- `symbol_memory_packet`
  - sourced from selected-symbol / refresh memory when available

Not implemented yet:

- true weekly aggregation builder
- true monthly aggregation builder

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
