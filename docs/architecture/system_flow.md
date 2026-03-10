# Trading Agent System - System Flow

## Integrated Chain Flow

1. Strategist
   - consumes global/news/sentiment context
   - fuses macro/market context (`index_trend`, `realized_volatility`, `market_breadth`, `macro_risk`)
   - can consume optional `kiwoom_market_summary` / `macro_context`
   - outputs structured strategic brief:
     - `market_regime`, `market_sentiment`, `key_events`
     - `themes`, `avoid_themes`, `playbook`
     - `scanner_bias` mode + `scanner_priority`, `trade_aggressiveness`, `risk_tone`
     - `monitor_guidance` mode (+ derived `monitor_policy`), `report_focus`
     - optional `candidates` hint
     - additive context quality fields (`regime_score`, `sentiment_score`, `news_context`, `theme_strength`)
2. Scanner
   - retrieves candidate universe from Kiwoom market data
   - source mix: condition search, top volume, top value, optional top change-rate, sector/theme map, watchlist
   - reduces pool before scoring (halt/abnormal/illiquid thresholds)
   - applies strategist theme/sector filter (`theme_map` / `sector_map`)
   - applies strategist scanner-priority guidance additively to ranking weights
   - applies strategist `playbook` additively to ranking weights
   - computes explainable score breakdown + features/risk
   - outputs `selected` and `top_stock` (final symbol selector in current run)
3. Monitor
   - entry/exit monitoring for selected stock only
   - emits `OrderIntent` (BUY/SELL/NOOP)
   - consumes strategist `monitor_policy` when provided
   - normal SELL exits require min-hold/cooldown/confirmation guards
   - duplicate SELL intents are suppressed by monitor-side pending-exit lock
   - emergency exits (`emergency_halt`, `news_shock`) are explicit separate path
4. Supervisor
   - applies approval + policy checks
5. Executor
   - executes only approved intents with guard precedence
6. Reporter
   - generates operator-facing summaries from logs/artifacts

## Minimal Decision Trace / Reason Ledger

- Additive cross-agent trace is emitted per `run_id`:
  - Strategist strategic frame snapshot
  - Scanner candidate/ranking selection snapshot
  - Monitor entry/exit decision snapshot
  - Supervisor verdict + guard reason snapshot
  - Executor execution attempt/result snapshot
- Runtime keys:
  - `decision_trace_ledger`
  - `reason_ledger` (alias)
- EventLog mirror:
  - `stage=decision_trace`

## Pipeline Role

- `graphs/pipelines/*`: when and in what order nodes run.
- `graphs/nodes/*`: node-level state transformation.
- `libs/*`: reusable pure/domain logic.

## Runtime Notes

- Polling runtime (`scripts/run_m13_live_loop.py`) remains loop-based.
- Tick pipeline can be selected:
  - `M13_TICK_PIPELINE=legacy_m10` (default compatibility path)
  - `M13_TICK_PIPELINE=integrated_chain` (Strategist -> Scanner -> Monitor chain)
- Guardrails are enforced in execution stage (`execute_from_packet`).
- Candidate source defaults to Kiwoom:
  - `CANDIDATE_SOURCE=kiwoom` (default)
  - fallback to strategist candidates when Kiwoom pool is empty
- Practical scanner tuning keys:
  - `TOP_CANDIDATE_POOL`
  - `MIN_TRADING_VALUE`
  - `MIN_VOLUME`
  - `ENABLE_THEME_FILTER`
  - `SCORE_WEIGHTS_*`
- Sell timing protections are applied in monitor/decision logic:
  - `MIN_HOLD_SECONDS`
  - `SELL_COOLDOWN` or `SELL_COOLDOWN_SEC`
  - `MONITOR_EXIT_CONFIRM_TICKS`

## Implementation Reference

- Canonical orchestrator: `graphs/commander_runtime.py`
- Canonical chain nodes:
  - Strategist: `graphs/nodes/strategist_node.py`
  - Scanner: `graphs/nodes/scanner_node.py`
  - Monitor: `graphs/nodes/monitor_node.py`
- Legacy compatibility modules remain for adapter/test support:
  - `libs/agent/commander.py`
  - `libs/agent/strategist.py`
  - `libs/agent/monitor.py`
