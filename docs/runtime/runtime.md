# Runtime Model

## TradeState (single source of truth)
- mode (mock/real)
- account snapshot
- positions + open orders
- current run_config / strategist_output / scan_result
- watchlist + latest signals

## EventLog (append-only)
- agent outputs
- skill calls + results
- approvals (audit)
- errors

**Goal:** make every run replayable.

## Runtime Decision Chain (Current)

1. Strategist writes:
   - `market_regime`, `market_sentiment`, `key_events`
   - `themes`, `avoid_themes`, `playbook`
   - `scanner_bias` mode, `scanner_priority`
   - `trade_aggressiveness`, `risk_tone`
   - `monitor_guidance` mode (+ derived `monitor_policy`), `report_focus`
   - `regime_score`, `sentiment_score`, `news_context`, `theme_strength` (additive quality fields)
   - `candidates` (Top-N, optional hint)
   - canonical `state["strategist_output"]` (contract: `libs/strategies/contracts.py::StrategistOutput`)
   - optional `strategist_llm` result snapshot (`status/model/applied/latency`) + EventLog `stage=strategist_llm`
2. Scanner uses Kiwoom market data as primary candidate source and writes:
   - `scanner_candidate_pool` (source, counts, theme-filter metadata)
   - `scan_results`
   - `ranked_candidates`
   - `selected`
   - `top_stock`
   - `scanner_output`
   - Candidate flow:
     - top volume/value/change-rate + condition search
     - sector/theme map + operator watchlist sources
     - pre-score pool reduction (halt/abnormal/illiquid filters)
    - optional theme/sector filter with `theme_map` / `sector_map`
    - additive strategist frame bias from `state["strategist_output"]` (`playbook`, `scanner_priority`, aggressiveness/risk tone)
     - strategist candidate fallback when Kiwoom pool is empty
     - static fallback-only pools can be blocked with `BLOCK_STATIC_FALLBACK_WHEN_KIWOOM_EMPTY=true`
     - strict mode (`STRICT_KIWOOM_CANDIDATES_ONLY=true`) blocks all strategist fallback on Kiwoom-empty
     - score output includes per-candidate `score_breakdown`
3. Monitor handles entry/exit only and writes:
   - `intents`
   - `monitor_exit`
   - `monitor_output`
   - Normal exit stabilization:
     - `MIN_HOLD_SECONDS` blocks premature SELL after entry fill.
     - `SELL_COOLDOWN`/`SELL_COOLDOWN_SEC` suppresses repeated SELL across loops.
     - `MONITOR_EXIT_CONFIRM_TICKS` requires consecutive exit confirmations.
   - Explicit emergency exit path:
     - `emergency_halt` / `news_shock` bypass normal confirmation as intentional hard-risk exits.
   - Strategist `monitor_policy` is consumed deterministically from `state["strategist_output"]` when present.
   - Monitor observability fields include:
     - `position_age_seconds`
     - `exit_signal_detected`
     - `exit_confirm_count`
     - `min_hold_blocked`
     - `sell_cooldown_blocked`
     - `monitor_reason`
4. Supervisor/Executor remain the only approval/execution path.

## Minimal Decision Trace / Reason Ledger (Additive)

- Runtime keys:
  - `state["decision_trace_ledger"]`
  - `state["reason_ledger"]` (alias)
- Per-run snapshots are appended by:
  - Strategist, Scanner, Monitor, Supervisor, Executor
- Snapshot intent:
  - compact, structured, parseable records for post-run analysis
  - no control-flow impact, no trading-logic mutation
- EventLog mirror:
  - `stage=decision_trace`

## Evidence Ledger (Raw Reasoning Trace, Additive)

- Append-only JSONL:
  - default `data/evidence_ledger/events.jsonl`
  - override `EVIDENCE_LEDGER_PATH`
- Canonical record keys:
  - `run_id`, `timestamp`, `agent`, `stage`
  - `raw_input`, `llm_prompt`, `llm_response`, `parsed_output`, `decision_link`
- Current runtime hooks:
  - Strategist: context snapshot + strategist LLM prompt/response + strategic bridge
  - Scanner: candidate retrieval/ranking snapshot + selected symbol bridge
  - Monitor: entry/exit snapshot + guard/trigger bridge
  - Reporter: post-run analysis input + optional AI review prompt/response
- Safety boundary:
  - Evidence ledger is observability-only and must not mutate runtime state or execution behavior.

## Canonical vs Compatibility Modules

- Canonical runtime orchestrator: `graphs/commander_runtime.py`
- Canonical strategist/scanner/monitor nodes:
  - `graphs/nodes/strategist_node.py`
  - `graphs/nodes/scanner_node.py`
  - `graphs/nodes/monitor_node.py`
- Compatibility modules kept for legacy contracts/tests:
  - `libs/agent/commander.py`
  - `libs/agent/strategist.py`
  - `libs/agent/scanner.py`
  - `libs/agent/monitor.py`

## M13 Tick Pipeline Selection

- `scripts/run_m13_live_loop.py` supports two tick paths:
  - `legacy_m10` (default): `m13_tick -> m10_live_pipeline -> decide_trade -> execute_from_packet`
  - `integrated_chain`: `m13_tick -> commander_runtime(mode=integrated_chain)`
- Control knobs:
  - CLI: `--tick-pipeline legacy_m10|integrated_chain`
  - ENV: `M13_TICK_PIPELINE`
- Symbol requirement:
  - `legacy_m10` requires `symbol`
  - `integrated_chain` can run without a preselected symbol

## Operational Visibility

- Runtime/agent visibility reference:
  - `docs/runtime/agent_visibility_runbook.md`
- Reporter passive analysis artifacts (`scripts/run_reporter_analysis_report.py`):
  - deterministic baseline remains canonical
  - optional AI review layer can be enabled without changing runtime decisions
  - `trade_summary`, `decision_chains`
  - `decision_trace_chain_summary`
  - `strategist_evaluation`, `scanner_evaluation`, `monitor_evaluation`
  - `supervisor_activity`, `incident_postmortem`, `improvement_suggestions`
  - `operator_facing_summary`, `developer_facing_summary`
  - optional AI fields:
    - `ai_summary`, `ai_findings`, `ai_root_causes`
    - `ai_improvement_suggestions`, `ai_run_grade`, `ai_agent_evaluations`
