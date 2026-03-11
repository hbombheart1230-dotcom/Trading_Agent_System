# Agents

## Commander
- Orchestrates one full run cycle.
- Routes state between Strategist, Scanner, Monitor, Supervisor, and Executor.
- Handles retry/pause/cancel transitions and runtime mode selection.
- Never sends orders directly.
- Canonical implementation: `graphs/commander_runtime.py`
- Compatibility layers:
  - `graphs/nodes/commander_node.py` (thin runtime wrapper)
  - `libs/agent/commander.py` (legacy adapter/scaffolding)

## Strategist
- Consumes market/news/global context.
- AI-centered strategic brain for daily framing (not final stock picker).
- Produces a structured strategic brief each run:
  - `market_regime`, `market_sentiment`, `key_events`
  - `themes`, `avoid_themes`, `playbook`
  - `scanner_bias` (`large_cap|leader|momentum|value`), `scanner_priority`
  - `trade_aggressiveness`, `risk_tone`
  - `monitor_guidance` (`hold_through_noise|defensive_exit|quick_take_profit`), `report_focus`
- May provide candidate hints (Top-N) as an additive signal.
- Strategist defines HOW to fight; final stock selection remains Scanner responsibility.
- Emits additive strategist contract fields in canonical `state["strategist_output"]`.
- Canonical DTO contract: `libs/strategies/contracts.py::StrategistOutput`.
- Strengthened context inputs include:
  - global sentiment signal health
  - news sentiment signal health + average score
  - market context (`index_trend`, `realized_volatility`, `market_breadth`, `macro_risk`)
  - optional `kiwoom_market_summary` and `macro_context`
- Canonical implementation: `graphs/nodes/strategist_node.py`
- Compatibility layer: `libs/agent/strategist.py` (normalizes strategist output for legacy `Plan` usage)

## Scanner
- Uses Kiwoom market data as primary candidate source in integrated chain.
- Candidate sources include condition search, top-volume, top-value, optional top-change-rate, sector/theme map, and operator watchlist.
- Applies theme/sector filtering from strategist output (`themes`) with `theme_map` / `sector_map`.
- Applies strategist ranking guidance (`scanner_priority`, aggressiveness/risk tone) additively to score weights.
- Applies strategist `playbook` additively to scoring weights (scanner still performs final quantitative selection).
- Scanner reads strategist frame from canonical `state["strategist_output"]`.
- Falls back to strategist candidates when Kiwoom candidate pool is empty.
- Scanner is the final Top-1 selector within strategist framing (not a blind picker).
- Reduces candidate pool with practical filters (halted/abnormal/illiquid thresholds).
- Computes practical score factors (trading-value, momentum, trend, volume-surge, intraday strength, penalties).
- Returns ranked list and Top-1 selection:
  - `scan_results`
  - `ranked_candidates`
  - `selected`
  - `top_stock`
  - `scanner_output`
- Canonical implementation: `graphs/nodes/scanner_node.py`
- Compatibility stage helper: `graphs/nodes/scan_candidates.py`

## Monitor
- Focuses on entry/exit only for the selected stock.
- Must not rescan/re-rank market universe.
- Emits buy/sell/noop intents from policy + position state.
- Applies sell guards (min hold, sell cooldown, exit confirmation).
- Consumes strategist `monitor_policy` when present (deterministic guard tuning).
- Monitor reads strategist frame from canonical `state["strategist_output"]`.
- Suppresses duplicate SELL intents with pending-exit lock/cooldown state across polling loops.
- Keeps emergency exits (`emergency_halt`, `news_shock`) explicit and separate from normal exit confirmation flow.
- Never executes orders.
- Canonical implementation: `graphs/nodes/monitor_node.py`
- Compatibility interface: `libs/agent/monitor.py` (legacy placeholder)

## Supervisor
- Owns approval and risk policy checks.
- Can approve/reject/modify intents.
- Guard precedence always overrides approval.

## Executor
- Executes approved intents only.
- Applies execution guards (optional `SYMBOL_ALLOWLIST`, max qty/notional, mode checks).
- Keeps mock/real separation.

## Reporter
- Builds operator-facing summaries from event logs and reports.
- Works as a post-run/report script layer (not a runtime control node).
- Does not change runtime decisions.
- Two-layer passive analysis:
  - deterministic structured analysis (baseline)
  - optional AI review layer on top of deterministic outputs
- AI review is post-run/read-only and never writes execution/runtime control state.
- Reporter-ready reason inputs are now emitted via:
  - `state["decision_trace_ledger"]` / `state["reason_ledger"]`
  - EventLog `stage=decision_trace`
- Runtime report generators: `libs/reporting/*`, `scripts/run_*report*.py`
- Enhanced passive analysis output (`reporter_analysis.v1`) includes:
  - `trade_summary` and per-trade decision summaries (buy/sell reason, hold duration, exit trigger)
  - `decision_chains` (run_id-based decision -> supervisor -> execution trace)
  - `decision_trace_chain_summary` (strategist/scanner/monitor/supervisor/executor chain completeness by run_id)
  - `strategist_evaluation`, `scanner_evaluation`, `monitor_evaluation`
  - `supervisor_activity` (block/approve frequency + reasons)
  - `operator_facing_summary` and `developer_facing_summary`
  - overtrading diagnostics, incidents/post-mortem, and `improvement_suggestions`
  - optional AI review fields:
    - `ai_summary`, `ai_findings`, `ai_root_causes`
    - `ai_improvement_suggestions`, `ai_run_grade`, `ai_agent_evaluations`
