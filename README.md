# Trading Agent System

## Enterprise Architecture Overview (M20)

Generated: 2026-02-14 13:29:06

------------------------------------------------------------------------

# 1. Vision

Trading Agent System is a LangGraph-oriented, multi-agent automated trading system designed with enterprise-grade safety, governance, and extensibility.

Core philosophy:

- Agents decide. They never execute directly.
- Execution is always gated.
- Guards override approvals.
- DTO contracts are stable.
- Every run is traceable.
- LLM is advisory only (never execution authority).

------------------------------------------------------------------------

# 2. System at a Glance (7-Agent Model)

    Commander (지휘관)
        ↓
    Strategist (전략가)
        ↓
    Scanner (스캐너)
        ↓
    Monitor (모니터)
        ↓
    Supervisor (감독관)
        ↓
    Executor (수행자)
        ↓
    Broker (Mock/Real)
        ↓
    Reporter (리포터)

Key separation:
- Decision Layer (Commander, Strategist, Scanner, Monitor)
- Approval Layer (Supervisor)
- Execution Layer (Executor + Guards)
- Observability Layer (Reporter + EventLog)

### Runtime Candidate Flow (M31+ additive)

The decision chain now uses Kiwoom market data as the primary candidate source:

1. Global news/sentiment context
2. Strategist builds a per-cycle strategic brief (`market_regime`, sentiment, playbook, scanner/monitor/reporter guidance)
   and may provide optional candidate hints
3. Scanner builds candidate pool from Kiwoom sources:
   - condition search
   - top volume ranking
   - top trading value ranking
   - top change-rate ranking (optional)
   - sector/theme mapped symbols
   - operator watchlist shortlist (optional)
4. Scanner applies theme/sector filtering (`theme_map`/`sector_map`) and ranks candidates
5. Scanner returns Top-1 (`top_stock`)
6. Monitor handles entry/exit intent generation only
7. Supervisor/Executor keep approval + guard + execution separation

Notes:
- Samsung-only trading is **not** the target architecture.
- `005930` in examples is illustrative sample data.
- `SYMBOL_ALLOWLIST` is an optional operational guard.
- `CANDIDATE_SOURCE=kiwoom` is the default path.
- Strategist candidates remain a compatibility fallback when Kiwoom pool is empty.
- Pure static fallback pools can be blocked with `BLOCK_STATIC_FALLBACK_WHEN_KIWOOM_EMPTY=true` (default).
- All strategist fallback can be disabled with `STRICT_KIWOOM_CANDIDATES_ONLY=true` (strict mode).
- Fallback candidate symbols can be overridden with `FALLBACK_CANDIDATE_SYMBOLS`.
- Candidate reduction knobs:
  - `TOP_CANDIDATE_POOL`
  - `MIN_TRADING_VALUE`
  - `MIN_VOLUME`
  - `ENABLE_THEME_FILTER`
- Practical score weights can be tuned with `SCORE_WEIGHTS_*`.
- Live loop tick path is selectable with `M13_TICK_PIPELINE`:
  - `legacy_m10` (default compatibility path)
  - `integrated_chain` (Strategist -> Scanner -> Monitor)

### Canonical Implementation Map (Role Boundaries)

- Commander (canonical orchestrator):
  - `graphs/commander_runtime.py`
  - `graphs/nodes/commander_node.py` is a thin wrapper around canonical runtime
  - `libs/agent/commander.py` is legacy compatibility scaffolding
- Strategist (canonical):
  - `graphs/nodes/strategist_node.py`
  - `libs/agent/strategist.py` is a thin compatibility adapter for legacy `Plan` contract
- Scanner (canonical):
  - `graphs/nodes/scanner_node.py` (Kiwoom-first candidate retrieval/ranking, strategist-guided)
  - `graphs/nodes/scan_candidates.py` remains compatibility stage wiring
- Monitor (canonical):
  - `graphs/nodes/monitor_node.py` (entry/exit intent logic only)
  - `libs/agent/monitor.py` is legacy placeholder interface
- Supervisor / Executor:
  - approval/risk via `libs/risk/supervisor.py` and execution guards in `graphs/nodes/execute_from_packet.py`
  - broker execution adapters in `libs/execution/executors/*`
- Reporter:
  - report generation in `libs/reporting/*` and scripts under `scripts/run_*report*.py`

Example strategist output:

```json
{
  "market_regime": "risk_on",
  "market_sentiment": "bullish",
  "key_events": [
    "global_sentiment score=0.320 status=ok source=yfinance",
    "news_signal_health unavailable=0 fallback=2"
  ],
  "themes": ["semiconductor", "AI"],
  "avoid_themes": ["thin_liquidity_names"],
  "playbook": "breakout",
  "scanner_bias": "momentum",
  "scanner_priority": ["momentum", "trend_strength", "volume_surge", "liquidity"],
  "trade_aggressiveness": "high",
  "risk_tone": "aggressive",
  "monitor_guidance": "hold_through_noise",
  "monitor_policy": {"min_hold_seconds": 900, "sell_cooldown_seconds": 360, "exit_confirm_ticks": 3},
  "regime_score": 0.41,
  "sentiment_score": 0.36,
  "news_context": {"ok": 5, "fallback": 0, "unavailable": 0, "avg_score": 0.22},
  "market_context_inputs": {"index_trend": 0.32, "realized_volatility": 0.019, "market_breadth": 0.58, "macro_risk": 0.22},
  "theme_strength": {"semiconductor": 0.71, "AI": 0.63},
  "report_focus": ["theme_accuracy", "scanner_fit", "exit_quality", "overtrading"],
  "candidates": ["005930", "000660", "042700", "058470", "091990"]
}
```

Example scanner output:

```json
{
  "candidate_pool_size": 24,
  "ranked_candidates": [
    {
      "symbol": "005930",
      "score_total": 0.87,
      "score_breakdown": {
        "trading_value": 0.18,
        "momentum": 0.24,
        "trend": 0.20,
        "volume_surge": 0.15,
        "risk_penalty": -0.10
      }
    }
  ],
  "top_stock": "005930",
  "top_score": 0.87
}
```

------------------------------------------------------------------------

# 3. Agent Responsibilities

## Commander (지휘관)
- Orchestrates full run cycle
- Decides which agent to call next
- Routes outputs between agents
- Handles abnormal events (guard block, LLM failure, emergency stop)
- Never selects stocks directly
- Never executes trades

## Strategist (전략가)
- AI-centered strategic framing (no order execution)
- Produces a structured run-cycle brief:
  - market regime/sentiment and key events
  - leading themes and avoid-themes
  - playbook, aggressiveness, and risk tone
  - scanner ranking priorities, monitor guidance, reporter focus
- Strengthened context inputs (additive):
  - global sentiment signal (status/source aware)
  - news sentiment + signal health
  - market context (`index_trend`, `realized_volatility`, `market_breadth`, `macro_risk`)
  - optional `kiwoom_market_summary` / `macro_context`
  - theme scores and candidate/theme-map fit
- May provide candidate hints (optional compatibility path)
- Writes additive guidance via canonical `state["strategist_output"]`
- Optional LLM strategic-frame stage (additive):
  - when enabled, Strategist calls LLM with news/global sentiment + market context
  - LLM returns frame overrides (`themes`, `playbook`, `scanner_priority`, `monitor_guidance`, etc.)
  - deterministic strategist logic remains baseline fallback on error/parse-fail
  - observability: EventLog `stage=strategist_llm`, `event=result`
- Canonical strategist contract is defined at `libs/strategies/contracts.py::StrategistOutput`

## Scanner (스캐너)
- Builds candidate universe from Kiwoom market data
- Applies strategist theme/sector filters when mapping exists
- Applies strategist frame additively to ranking:
  - `playbook`, `scanner_bias`, `scanner_priority`, `risk_tone`, `trade_aggressiveness`
- Scanner guidance is sourced from canonical `state["strategist_output"]` (with backward-compatible `scanner_guidance` override hook)
- Reduces pool with practical guards (halt/abnormal/illiquid thresholds)
- Computes explainable scoring factors (value, momentum, trend, volume surge, intraday strength, risk penalties)
- Ranks candidates with score breakdown and selects Top-1

## Monitor (모니터)
- Watches selected primary symbol / active position state
- Emits ActionProposal / OrderIntent only
- Consumes strategist guidance deterministically:
  - `monitor_guidance`, `risk_tone`, `trade_aggressiveness`, `monitor_policy`
- Monitor guidance is sourced from canonical `state["strategist_output"]`
- Normal SELL exits are stabilized with:
  - `MIN_HOLD_SECONDS`
  - `SELL_COOLDOWN` (`SELL_COOLDOWN_SEC` alias)
  - `MONITOR_EXIT_CONFIRM_TICKS`
- Emergency exits (`emergency_halt`, `news_shock`) are handled as explicit separate path
- Never selects stocks and never places orders

## Supervisor (감독관)
- Owns risk limits and policy
- Validates OrderIntent
- Approves / rejects / modifies
- Can pause/stop system

## Executor (수행자)
- Executes approved intents only
- Applies guard precedence
- Ensures idempotency
- Routes to Broker API

## Reporter (리포터)
- Reads EventLog
- Produces script-driven daily / trade / operator reports from artifacts
- Summarizes LLM quality and execution metrics
- Two-layer post-run model:
  - deterministic structured analysis baseline
  - optional AI review layer (`reporter_ai_review`) over deterministic artifacts
- Produces passive post-run analysis sections:
  - `trade_summary`, `decision_chains`
  - `decision_trace_chain_summary` (run_id chain completeness + per-agent summary)
  - `strategist_evaluation`, `scanner_evaluation`, `monitor_evaluation`
  - `supervisor_activity`, `incidents`, `improvement_suggestions`
  - `operator_facing_summary`, `developer_facing_summary`
- Optional AI review output fields:
  - `ai_summary`, `ai_findings`, `ai_root_causes`
  - `ai_improvement_suggestions`, `ai_run_grade`, `ai_agent_evaluations`
- Does not participate in runtime decision routing
- AI review remains passive/post-run only and never influences live trading decisions

------------------------------------------------------------------------

# 4. Execution & Guard Model

Execution occurs only when:

- APPROVAL_MODE permits
- EXECUTION_ENABLED = true
- Real mode explicitly allowed
- If `SYMBOL_ALLOWLIST` is configured, symbol must be allowlisted
- Max qty/notional limits respected
- Intent not already executed

Guard priority always overrides approval.

------------------------------------------------------------------------

# 5. Intent Lifecycle

    created → pending_approval → approved → executing → executed/failed → settled

Idempotency enforced via intent_id.

------------------------------------------------------------------------

# 6. LLM Architecture (M20)

Current State:
- OpenRouter integration via OpenAI-compatible adapter
- Provider-agnostic LLM interface
- JSON intent normalization: { "intent": ... }
- Schema validation enforced
- Retry with exponential backoff
- Error-type classification
- LLM telemetry logging (`stage=strategist_llm`)
- Operator smoke and query scripts for LLM telemetry

Implemented Milestones:
- M20-1: strategist smoke + safe fallback
- M20-2: adapter parsing + normalization + retry/telemetry
- M20-3: legacy LLM router compatibility fix
- M20-4: smoke visibility options + event query CLI
- M20-5: daily metrics aggregation for strategist LLM reliability
- M20-6: prompt/schema version telemetry and distribution metrics
- M20-7: token usage + estimated cost telemetry in events/ops/metrics

Next Steps:
- Circuit breaker + safe fallback mode
- LangGraph formal state machine orchestration

------------------------------------------------------------------------

# 7. Observability

Every run includes a run_id.

Event log (JSONL):

- ts
- run_id
- stage
- event
- payload
- error_type (if applicable)
- latency_ms (LLM/execution)

LLM telemetry tracked separately from trading logic.

Minimal Decision Trace / Reason Ledger (additive):
- `state["decision_trace_ledger"]` (alias: `state["reason_ledger"]`)
- linked by `run_id`
- compact snapshots from:
  - Strategist (`market_regime`, `themes`, `playbook`, `scanner_bias`, `risk_tone`, `monitor_guidance`)
  - Scanner (`candidate_pool_size`, `top_candidates`, `selected_symbol`, `score_breakdown_summary`)
  - Monitor (`entry_reason`, `exit_reason`, `position_age_seconds`, sell-guard flags, `monitor_reason`)
  - Supervisor/Executor (`verdict`, `guard_reason`, execution attempt/result summary)
- mirrored to EventLog as `stage=decision_trace` for post-run analysis and future reporter upgrades

Operator-facing report scripts:
- `python -m scripts.run_operator_daily_summary --event-log-path data/logs/events.jsonl --report-dir reports/operator_summary --day <YYYY-MM-DD>`
- `python -m scripts.run_decision_story_report --event-log-path data/logs/events.jsonl --report-dir reports/decision_story --day <YYYY-MM-DD>`
- `python -m scripts.run_run_card_report --event-log-path data/logs/events.jsonl --report-dir reports/run_cards --day <YYYY-MM-DD>`
- `python -m scripts.run_trade_explain_report --event-log-path data/logs/events.jsonl --report-dir reports/trade_explain --day <YYYY-MM-DD>`
- `python -m scripts.run_reporter_analysis_report --event-log-path data/logs/events.jsonl --intents-path data/logs/intents.jsonl --report-dir reports/reporter_analysis --day <YYYY-MM-DD>`
- Reporter AI review optional flags:
  - `--ai-review` (enable passive AI review stage)
  - `--no-ai-review` (force deterministic-only mode)
  - `--ai-review-model <model>` (override reporter model route)

------------------------------------------------------------------------

# 8. Security & Governance

- .env never committed
- Real execution disabled by default
- Two-person review recommended for real mode
- LLM has zero execution authority
- Execution always guarded

------------------------------------------------------------------------

# 9. Deployment Model

Phase 1: Script-based execution  
Phase 2: Container + scheduler  
Phase 3: Full LangGraph orchestration  
Phase 4: Metrics + alerting + circuit breaker  

------------------------------------------------------------------------

# 10. Testing Coverage

- mock/manual/auto modes
- real mode guard enforcement
- max qty / max notional guard
- legacy AUTO_APPROVE compatibility
- manual approval reproducibility
- LLM schema validation tests

------------------------------------------------------------------------

# 11. Roadmap

M20:
- LangGraph orchestration
- Provider-agnostic LLM integration
- Schema validation enforcement
- LLM retry/telemetry and operator tooling

M21:
- Circuit breaker
- Safe fallback mode
- Telemetry dashboard

M22+:
- Cost optimization layer
- Multi-provider LLM routing
- Strategy evaluation framework

------------------------------------------------------------------------

# Enterprise Guarantee

This architecture ensures:

- Safety before profit
- Deterministic risk boundaries
- Auditable execution chain
- Scalable agent intelligence
- Provider-agnostic LLM extensibility
