# Symbol Memory Contract (2026-04-19)

## Goal

This contract defines symbol-specific memory.

This memory exists to answer:

- how this symbol has behaved historically
- which playbooks fit or fail on this symbol
- whether execution risk is elevated
- whether the symbol deserves a deterministic bonus, penalty, or policy adjustment

## Critical Ordering Rule

Symbol memory is not primary pre-selection strategist memory.

Reason:

- strategist runs before final symbol selection
- scanner chooses candidates before a final selected symbol exists

Therefore:

1. symbol memory should be used deterministically during scanner ranking
2. symbol memory may be sent to LLM only after symbol selection or during long-hold refresh

## Consumers

Primary consumers:

- `graphs/nodes/scanner_node.py`
- selected-symbol strategist refresh
- `graphs/nodes/monitor_node.py` through inherited policy or compact selected-symbol context

Not a primary consumer:

- the first strategist call

## Canonical Path

Current canonical path:

- `reports/symbols/<SYMBOL>/symbol_memory.json`

Current adjacent source material:

- `reports/symbols/<SYMBOL>/symbol_trade_report.json`
- `reports/symbols/<SYMBOL>/trade_history.json`
- `reports/symbols/<SYMBOL>/latest_snapshot.json`

Path policy:

- do not create a parallel `reports/strategy_memory/symbols/*` root right now
- keep `reports/symbols/*` as the canonical symbol-memory surface
- if operator-facing symbol prose becomes unnecessary later, prune that prose around the canonical `symbol_memory.json` rather than duplicating paths

## Required Content

1. basic trade history
- recent trade count
- recent win rate
- average return
- average peak runup / peak drawdown

2. playbook-specific behavior
- breakout count and win rate
- pullback count and win rate
- dominant failure reasons by playbook

3. execution risk
- spread bps distribution
- slippage tendency if available
- quote instability tendency if available

4. monitor behavior
- repeated blockers
- common reject reasons
- hold refresh effectiveness

5. deterministic bias recommendation
- scanner bonus / penalty
- preferred playbook
- discouraged playbook
- risk cap recommendation

## Minimal JSON Shape

```json
{
  "symbol": "005930",
  "window_label": "recent_20d",
  "trade_stats": {
    "trade_count": 14,
    "win_rate": 0.36,
    "avg_return_pct": -0.004,
    "avg_peak_runup_pct": 0.006,
    "avg_peak_drawdown_pct": -0.012
  },
  "playbook_stats": {
    "breakout": {
      "count": 9,
      "win_rate": 0.22,
      "dominant_failures": ["too_extended_from_vwap", "volume_confirmation_failed"]
    },
    "pullback": {
      "count": 5,
      "win_rate": 0.60
    }
  },
  "execution_risk": {
    "spread_bps_p50": 18,
    "spread_bps_p90": 42,
    "slippage_bps_p50": 11
  },
  "monitor_patterns": {
    "repeated_blockers": ["breakout_readiness", "confirmed_entry"],
    "hold_refresh_effective_rate": 0.20
  },
  "bias_recommendation": {
    "scanner_penalty": 0.08,
    "prefer_playbook": "pullback",
    "avoid_playbook": "breakout",
    "risk_cap": "conservative"
  }
}
```

## Usage Rule

### Scanner

Scanner should use symbol memory deterministically.

Examples:

- apply symbol penalty to fragile playbooks
- apply spread/slippage penalty
- apply playbook compatibility bonus
- cap ranking confidence if historical behavior is unstable

### Selected-Symbol Refresh

If a selected symbol exists, strategist refresh may read a compact symbol memory packet.

This is not a new scanner LLM.
This is a second strategist refresh with selected-symbol context.

### Monitor

Monitor should not become a new LLM consumer.
It should execute updated policy or compact deterministic priors.

## Source Reports

Preferred sources:

- `reports/trades`
- deterministic trade read model
- canonical execution artifacts
- `reports/daily`
- `reports/metrics`
- `reports/symbols/<SYMBOL>/symbol_trade_report.json`
- `reports/symbols/<SYMBOL>/latest_snapshot.json`

Reinterpretation target:

- existing `reports/symbols` should not remain a generic operator surface
- it should be redefined as strategy memory source material for symbol history

## Design Rule

If a symbol-memory field cannot justify one of the following, it should be removed:

- scanner bonus
- scanner penalty
- selected-symbol policy adjustment
- execution risk warning
