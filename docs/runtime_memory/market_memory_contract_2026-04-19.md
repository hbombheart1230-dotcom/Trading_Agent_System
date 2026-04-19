# Market Memory Contract (2026-04-19)

## Goal

This contract defines the pre-selection memory that should shape the first strategist decision.

This memory is not symbol-specific.
It exists to help the system behave like a trader who first reads the market, then chooses a playbook.

## Role

Market memory answers questions such as:

- what kind of day is this
- which playbooks have recently worked or failed
- whether the system should stay conservative or allow limited loosening
- whether repeated failure patterns require baseline policy adjustment

This memory is for broad framing only.
It must not depend on a final selected symbol.

## Consumers

Primary consumer:

- `graphs/nodes/strategist_node.py`

Secondary consumers:

- optional operator briefing
- post-run diagnostics

Not a direct consumer:

- `graphs/nodes/scanner_node.py`
- `graphs/nodes/monitor_node.py`

Scanner and monitor may inherit policies that originated from market memory, but they should not read market memory as a primary source.

## Horizons

Canonical horizons:

- daily now
- weekly later
- monthly later
- aggregate later

Current canonical path:

- `reports/performance/<day>/strategy_memory.json`

Current adjacent artifacts:

- `reports/performance/<day>/summary.json`
- `reports/performance/<day>/playbook_stats.json`
- `reports/performance/<day>/symbol_stats.json`

Path policy:

- do not introduce a parallel `reports/strategy_memory/*` root right now
- extend the existing `reports/performance/*` surface instead
- add weekly / monthly / aggregate files under `reports/performance/*` only when a real consumer exists

## Required Content

Each market memory packet should contain compressed, decision-relevant summaries only.

Required sections:

1. market regime summary
- regime
- volatility tone
- news/global sentiment summary
- breadth / participation summary if available

2. recent system performance summary
- recent trade count
- recent win/loss/noop distribution
- recent hold-to-exit behavior
- dominant route mix

3. playbook performance summary
- breakout performance
- pullback performance
- reversal performance if enabled
- defensive posture effectiveness

4. repeated failure patterns
- dominant failure reasons
- repeated blockers
- overtrading / false entry / missed entry tendencies

5. adjustment recommendation summary
- tighten / relax / keep conservative
- bounded reasoning only
- no direct order instruction

6. compressed reporter-analysis state
- system health
- route mix
- current scanner selection status
- current monitor status
- dominant monitor reasons
- dominant scanner source mix
- top supervisor blockers
- report focus targets
- incident count

## Minimal JSON Shape

```json
{
  "horizon": "daily",
  "period_key": "2026-04-19",
  "market_summary": {
    "market_regime": "neutral",
    "volatility_tone": "contained",
    "global_sentiment_score": 0.03,
    "news_bias": "mixed"
  },
  "system_summary": {
    "recent_trade_count": 12,
    "noop_ratio": 0.33,
    "hold_extension_ratio": 0.17
  },
  "playbook_performance": {
    "breakout": {
      "count": 7,
      "win_rate": 0.29,
      "dominant_failures": ["too_extended_from_vwap"]
    },
    "pullback": {
      "count": 5,
      "win_rate": 0.60
    }
  },
  "failure_patterns": {
    "dominant_failure_patterns": ["late_breakout_entry", "volume_confirmation_failed"],
    "repeated_blockers": ["confirmed_entry", "breakout_readiness"]
  },
  "adjustment_recommendation": {
    "direction": "tighten",
    "reason": "recent false breakouts dominate defensive sessions",
    "confidence": "medium"
  }
}
```

## Source Reports

Preferred sources:

- `reports/daily/<day>`
- `reports/metrics`
- `reports/dev/analysis/reporter_analysis`
- deterministic trade read model and canonical artifacts
- `reports/performance/<day>/summary.json`
- `reports/performance/<day>/playbook_stats.json`

Do not use as primary sources:

- `reports/decision_story`
- `reports/run_cards`
- top-level `reports/trade_explain`

## LLM Usage Rule

Market memory is intended for the first strategist LLM call.

It should be injected as compact structured context.
It should not be a long-form report dump.

## Design Rule

If a memory field cannot plausibly influence:

- playbook choice
- risk tone
- monitor baseline

it does not belong in market memory.
