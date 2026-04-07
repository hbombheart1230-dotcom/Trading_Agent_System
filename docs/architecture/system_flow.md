# Trading Agent System - System Flow

## Integrated Chain Flow

1. Strategist
   - consumes global/news/sentiment context
   - derives market-news query targets before final stock selection when no stock symbols are yet available
   - fuses macro/market context (`index_trend`, `realized_volatility`, `market_breadth`, `macro_risk`)
   - can consume optional `kiwoom_market_summary` / `macro_context`
   - outputs structured strategic brief:
     - `market_regime`, `market_sentiment`, `key_events`
     - `themes`, `avoid_themes`, `playbook`
     - `scanner_bias` mode + `scanner_priority`, `scanner_source_policy`, `trade_aggressiveness`, `risk_tone`
     - `monitor_guidance` mode (+ derived `monitor_policy`), `report_focus`
     - `macro_stress_overlay` (soft macro-risk influence from VIX/DXY/TNX)
     - optional `candidates` hint
     - additive context quality fields (`regime_score`, `sentiment_score`, `news_context`, `theme_strength`)
     - canonical runtime key: `state["strategist_output"]` (DTO: `libs/strategies/contracts.py::StrategistOutput`)
     - additive advisory memory key: `state["recent_strategy_feedback"]`
2. Scanner
   - retrieves candidate universe from Kiwoom market data
   - source mix: condition search, top volume, top value, optional top change-rate, sector/theme map, watchlist
   - strategist can change the source mix itself through `scanner_source_policy`
   - hydrates candidate chart/feature packs before final ranking
     - prefers prebuilt `feature_engine.by_symbol`
     - otherwise hydrates candidate-level features inside scanner path
   - reduces pool before scoring (halt/abnormal/illiquid thresholds)
   - applies strategist theme/sector filter (`theme_map` / `sector_map`)
   - applies strategist scanner-priority guidance additively to ranking weights
   - applies strategist `playbook` additively to ranking weights
   - strategist guidance source: `state["strategist_output"]` (with backward-compatible override hooks)
   - computes explainable score breakdown + features/risk
   - carries quote/feature observability such as:
     - `feature_source`
     - `feature_symbol_count`
     - `skill_quote_price`
     - `quote_volume`
     - `quote_trading_value`
     - `intraday_change_pct`
   - outputs `selected` and `top_stock` (final symbol selector in current run)
3. Monitor
   - entry/exit monitoring for selected stock only
   - emits `OrderIntent` (BUY/SELL/NOOP)
   - consumes strategist `monitor_policy` when provided
   - strategist guidance source: `state["strategist_output"]`
   - normal SELL exits require min-hold/cooldown/confirmation guards
   - duplicate SELL intents are suppressed by monitor-side pending-exit lock
   - emergency exits (`emergency_halt`, `news_shock`) are explicit separate path
4. Supervisor
   - applies approval + policy checks
5. Executor
   - executes only approved intents with guard precedence
6. Reporter
   - generates operator-facing summaries from logs/artifacts
   - generates one-run full-chain artifact (`agent_pipeline_trace.v1`) from event log + evidence ledger
   - `reporter_analysis.v1` keeps deterministic analysis as baseline
   - appends compact strategy-memory records for future Strategist advisory context only
   - optional AI review stage can be enabled post-run (passive/read-only)
   - output includes `decision_trace_chain_summary`, `operator_facing_summary`, `developer_facing_summary`
   - optional AI fields: `ai_summary`, `ai_findings`, `ai_root_causes`, `ai_improvement_suggestions`, `ai_run_grade`

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

- Official trading runtime entrypoint is `scripts/run_session.py`.
- Intraday polling runtime remains loop-based through backend `scripts/run_m13_live_loop.py`.
- Tick pipeline can be selected:
  - `M13_TICK_PIPELINE=legacy_m10` (default compatibility path)
  - `M13_TICK_PIPELINE=integrated_chain` (Strategist -> Scanner -> Monitor chain)
- Commander runtime phase is explicit:
  - `preopen`: strategist warmup only
  - `session`: full trading path
  - `closeout`: passive closeout-ready state only
- Guardrails are enforced in execution stage (`execute_from_packet`).
- Candidate source defaults to Kiwoom:
  - `CANDIDATE_SOURCE=kiwoom` (default)
  - fallback to strategist candidates when Kiwoom pool is empty
  - static fallback-only candidate pools can be blocked via `BLOCK_STATIC_FALLBACK_WHEN_KIWOOM_EMPTY=true`
  - strict Kiwoom-only mode: `STRICT_KIWOOM_CANDIDATES_ONLY=true`
  - fallback symbols can be overridden via `FALLBACK_CANDIDATE_SYMBOLS`
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
- Read-only operator UI now sits on top of runtime artifacts:
  - overview is same-day aware and can fall back to live event-log summaries
  - `/runs` surfaces macro stress and feature coverage
  - `/runs/{run_id}` surfaces operator brief, feature coverage, quote metrics, same-day symbol history, and recent same-symbol run chain

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
