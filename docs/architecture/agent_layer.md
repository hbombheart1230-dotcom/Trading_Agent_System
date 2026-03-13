# Agent Layer

This document defines agent responsibilities and handoff boundaries.

## Goal

- Keep decision and execution responsibilities separated.
- Ensure agents create decisions/intents only.
- Keep all real broker execution inside execution layer with guard precedence.

## Responsibility Split

### Commander
- Orchestrates runtime path and node order.
- Owns transition/state routing and runtime-level events.
- Does not select symbols directly and does not execute broker APIs.

### Strategist
- AI-centered strategic brain for the run cycle.
- Builds high-level plan from market/news/global context.
- Emits:
  - `market_regime`
  - `market_sentiment`
  - `key_events`
  - `themes`
  - `avoid_themes`
  - `playbook`
  - `scanner_bias` (`large_cap|leader|momentum|value`)
  - `scanner_priority`
  - `trade_aggressiveness`
  - `risk_tone` (`conservative|normal|aggressive`)
  - `monitor_guidance` (`hold_through_noise|defensive_exit|quick_take_profit`)
  - `monitor_policy` (derived deterministic guard parameters)
  - `report_focus`
  - `recent_strategy_feedback` (compact Reporter-memory advisory summary)
  - `candidates` (Top-N, optional hint/fallback)
  - canonical `state["strategist_output"]` (`libs/strategies/contracts.py::StrategistOutput`)
- Strategist defines strategy frame; Scanner remains final symbol selector.
- Strategist can read recent Reporter findings from `data/strategy_memory/feedback.jsonl` as advisory context only.
- Additive context enrichment includes:
  - global/news signal health
  - market context inputs (`index_trend`, `realized_volatility`, `market_breadth`, `macro_risk`)
  - optional `kiwoom_market_summary` / `macro_context`
  - theme strength map

### Scanner
- Builds candidate universe from Kiwoom market data in integrated chain path.
- Candidate sources:
  - condition search
  - top volume
  - top trading value
  - top change-rate (optional)
  - sector/theme map symbols
  - operator watchlist
- Reduces candidate pool before scoring:
  - halted/abnormal exclusion
  - liquidity thresholds (`MIN_TRADING_VALUE`, `MIN_VOLUME`)
- Applies strategist theme/sector filtering when `theme_map` / `sector_map` is available.
- Applies strategist ranking guidance (`scanner_priority`, aggressiveness/risk tone) additively.
- Applies strategist `playbook` additively to score weighting.
- Scanner consumes strategist frame from `state["strategist_output"]` and remains final Top-1 selector.
- Falls back to strategist candidate hints when Kiwoom pool is empty.
- Produces:
  - `scan_results`
  - `ranked_candidates`
  - `selected`
  - `top_stock`
  - `scanner_output`
- Scanner must apply strategist framing (theme/bias/priority) and then select Top-1.

### Monitor
- Handles entry/exit logic for selected stock.
- Applies sell protections:
  - `MIN_HOLD_SECONDS`
  - `SELL_COOLDOWN` or `SELL_COOLDOWN_SEC`
  - `MONITOR_EXIT_CONFIRM_TICKS`
- Prevents duplicate SELL intent emission using loop-persistent pending-exit lock/cooldown state.
- Keeps emergency exits (`emergency_halt`, `news_shock`) explicit and separate from normal confirmation flow.
- Consumes strategist `monitor_policy` deterministically when present.
- Monitor consumes strategist guidance (`monitor_guidance`, `risk_tone`, `trade_aggressiveness`) from `state["strategist_output"]`.
- Emits `intents` only.
- Does not execute orders.
- Must not rescan or re-rank stock universe.

### Supervisor
- Evaluates approval/risk policy.
- Can approve/reject/modify before execution.

### Executor / Execution Layer
- Converts approved decision packet into broker request.
- Enforces execution guards and mode safety:
  - `EXECUTION_ENABLED`
  - `ALLOW_REAL_EXECUTION`
  - optional `SYMBOL_ALLOWLIST`
  - size/notional constraints
- Performs the only actual broker call path.

### Reporter
- Derives operator-readable summaries from logs/artifacts.
- Does not alter runtime decisions.
- Two-layer passive model:
  - deterministic structured analysis baseline
  - optional AI review stage for post-run interpretation
- AI review is read-only/post-run and does not write to live runtime control state.
- Reporter can persist compact strategy-memory records for future Strategist advisory context.
- `reporter_analysis.v1` adds:
  - `decision_trace_chain_summary` (run_id chain completeness across strategist/scanner/monitor/supervisor/executor)
  - `operator_facing_summary` (health + immediate actions)
  - `developer_facing_summary` (debug-first counters/reasons)
  - optional AI review fields:
    - `ai_summary`, `ai_findings`, `ai_root_causes`
    - `ai_improvement_suggestions`, `ai_run_grade`, `ai_agent_evaluations`

## Minimal Decision Trace / Reason Ledger

- Additive runtime ledger keys:
  - `state["decision_trace_ledger"]`
  - `state["reason_ledger"]` (alias)
- Per-run (`run_id`) snapshots are appended by:
  - Strategist, Scanner, Monitor, Supervisor, Executor
- EventLog mirror:
  - `stage=decision_trace`
- Purpose:
  - support post-run reporting and role-boundary audits without changing live decisions.

## Runtime Path Notes

- Integrated chain path:
  - Strategist -> Scanner -> Monitor -> Supervisor/Executor
- Legacy live tick path still exists for compatibility (`m10` pipeline).
- `scripts/run_m13_live_loop.py` can select tick pipeline with:
  - `--tick-pipeline legacy_m10`
  - `--tick-pipeline integrated_chain`
  - env `M13_TICK_PIPELINE`

## Implementation Ownership Map

- Commander (canonical): `graphs/commander_runtime.py`
  - wrappers: `graphs/nodes/commander_node.py`
  - legacy adapter: `libs/agent/commander.py`
- Strategist (canonical): `graphs/nodes/strategist_node.py`
  - legacy adapter: `libs/agent/strategist.py`
- Scanner (canonical): `graphs/nodes/scanner_node.py`
  - compatibility stage helper: `graphs/nodes/scan_candidates.py`
- Monitor (canonical): `graphs/nodes/monitor_node.py`
  - legacy interface: `libs/agent/monitor.py`
