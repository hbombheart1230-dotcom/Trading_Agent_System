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
- pytest default log isolation: when `EVENT_LOG_PATH` is unset under pytest, runtime nodes write to `data/logs/dev/testing/pytest_events.jsonl` instead of the operator log

**Goal:** make every run replayable.

## Runtime Decision Chain (Current)

1. Strategist writes:
   - `news_query_targets` (market/news search terms derived from global sentiment + macro context before final stock selection)
   - `global_sentiment_signal.index_moves` (`sp500_pct`, `nasdaq_pct`, `dow_pct`), `macro_moves` (`vix_pct`, `vix_level`, `dxy_pct`, `tnx_delta`), and `fear_index` (`^VIX` level/change/pressure) when available
   - `market_regime`, `market_sentiment`, `key_events`
   - `themes`, `avoid_themes`, `playbook`
   - `scanner_bias` mode, `scanner_priority`, `scanner_source_policy`
   - `macro_stress_overlay` (soft macro-risk influence summary from VIX/DXY/TNX context)
   - `trade_aggressiveness`, `risk_tone`
   - `monitor_guidance` mode (+ derived `monitor_policy`), strategist `exit_policy` baseline, `report_focus`
   - `regime_score`, `sentiment_score`, `news_context`, `candidate_news_context`, `market_news_context`, `theme_strength` (additive quality fields)
   - `candidates` (Top-N, optional hint)
   - canonical `state["strategist_output"]` (contract: `libs/strategies/contracts.py::StrategistOutput`)
   - advisory `state["recent_strategy_feedback"]` loaded from `data/strategy_memory/feedback.jsonl`
     - Strategist prefers deduped daily latest snapshots from `data/strategy_memory/daily/` when available
     - compact recent theme/playbook/monitor/scanner findings
     - advisory only; no hard runtime override
   - additive runtime `theme_map` / `sector_map` seeded from strategist candidate hints so scanner `sector_theme` source can remain non-zero even without a static operator map
   - optional `strategist_llm` result snapshot (`status/model/applied/latency`) + EventLog `stage=strategist_llm`
   - additive strategist LLM confidence fields:
     - `llm_frame_low_confidence`
     - `strategist_llm.low_confidence`
     - `strategist_llm.repair_used`
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
    - strategist-driven Kiwoom source policy from `state["strategist_output"]["scanner_source_policy"]`
      - default mock/operational baseline keeps `condition_search` disabled
      - example: `defensive` can disable `top_change_rate`
      - example: `breakout` can emphasize `top_change_rate` / `top_volume`
      - explicit opt-in (`KIWOOM_CANDIDATE_ENABLE_CONDITION_SEARCH=true`) can re-enable `condition_search`
     - scanner diagnostics now expose `condition_search_status`, `condition_search_source`, and `condition_search_reason` so operators can distinguish "zero candidates" from "source not integrated" or "baseline disabled"
     - integrated-chain scanner now hydrates candidate features before ranking:
       - prefers `state["feature_engine"]["by_symbol"]` when present
       - otherwise builds additive candidate feature packs through scanner-side hydration
     - scanner observability now includes candidate feature hydration / quote metrics such as:
       - `feature_source`
       - `feature_symbol_count`
       - `skill_quote_price`
       - `quote_volume`
       - `quote_trading_value`
       - `intraday_change_pct`
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
     - `POST_EXIT_COOLDOWN_SEC` suppresses immediate BUY re-entry after a SELL.
     - `MONITOR_EXIT_CONFIRM_TICKS` requires consecutive exit confirmations.
     - `max_hold` / `time_stop` remain normal exits and still respect min-hold/cooldown/confirmation.
   - Explicit emergency exit path:
     - `emergency_halt` / `news_shock` bypass normal confirmation as intentional hard-risk exits.
   - Strategist `monitor_policy` is consumed deterministically from `state["strategist_output"]` when present.
   - Strategist `exit_policy` is additive: it sets a playbook-aware exit baseline, then Monitor applies final feature/position-aware adjustments.
   - Monitor observability fields include:
     - `position_age_seconds`
     - `exit_signal_detected`
     - `exit_confirm_count`
     - `min_hold_blocked`
     - `sell_cooldown_blocked`
     - `monitor_reason`
4. Supervisor/Executor remain the only approval/execution path.
   - Execution observability now separates:
     - `mode`: executor selection (`mock|real`, kept for compatibility)
     - `execution_mode`: resolved `EXECUTION_MODE`
     - `kiwoom_mode`: broker environment selection (`mock|real`)
     - `broker_env`: effective broker target environment
     - `effective_mode`: operator-friendly interpretation such as `mock_executor`, `mock_broker_http`, `real_broker_http`

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
- Commander resolves both:
  - `runtime_mode`: `graph_spine|decision_packet|integrated_chain`
  - `runtime_phase`: `preopen|session|closeout`
- Phase behavior:
  - `preopen`: portfolio/risk hydration + strategist warmup, no scanner/monitor/execution
  - `session`: normal runtime path
  - `closeout`: passive commander closeout-ready state only; closeout reporting is handled by orchestration scripts
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
  - `integrated_chain` now hydrates scanner candidate features/quote metrics before final ranking, so chart/feature scoring is active during normal session runs

## Operational Visibility

- Runtime/agent visibility reference:
  - `docs/runtime/agent_visibility_runbook.md`
- Report inventory / cleanup reference:
  - `docs/runtime/report_management.md`
- Log inventory / cleanup reference:
  - `docs/runtime/log_management.md`
- Single-run full-chain trace artifact:
  - generator: `scripts/run_agent_pipeline_trace_report.py`
  - outputs: `reports/dev/analysis/agent_pipeline_trace/agent_pipeline_trace_<run>.md|json`
- Executed-run bundle artifact for session/closeout:
  - generator: `scripts/run_live_execution_bundle_report.py`
  - outputs: `reports/dev/analysis/live_execution_bundles/live_execution_bundle_<run>.md|json`
  - canonical per-trade story path: `reports/trades/YYYY/MM/<story_id>/`
  - canonical story files:
    - `aggregated_execution_bundle.json`
    - `trade_story_input.json`
    - `trade_report.json`
    - `trade_report.md`
  - closeout can auto-generate these bundles for BUY/SELL runs detected in the selected day
- Read-only operator web UI:
  - launcher:
    - `scripts/run_operator_ui.py`
    - PowerShell helpers: `scripts/start_operator_ui.ps1`, `scripts/stop_operator_ui.ps1`
  - default URL: `http://127.0.0.1:8010`
  - pages:
    - `/` latest same-day overview
      - `Today Trades`
      - `Today Traded Symbols`
      - `Overtrading Warning`
      - `Latest Strategist Prompt`
      - `Strategy Memory Timeline`
    - `/runs` recent commander-routed cycles
      - includes `macro stress` and `feature coverage`
    - `/runs/{run_id}` single-run commander -> strategist -> scanner -> monitor -> supervisor -> executor trace
      - includes operator-facing Korean brief
      - includes `Feature Coverage`, `Quote Metrics`
      - includes same-day symbol trade history and recent same-symbol run chain
    - `/healthz` machine-readable health endpoint
  - overview/report behavior:
    - overview uses exact same-day report files when they exist
    - it does not silently fall back to stale prior-day reporter/operator reports
    - if same-day reports are not generated yet, overview falls back to live event-log summaries
    - run detail explicitly surfaces `same_day_report_missing` instead of showing stale analysis
  - OpenRouter role routing:
    - `AI_STRATEGIST_MODEL=openrouter/auto` is the canonical strategist model key and lets Strategist use OpenRouter auto-routing across the full model pool
    - `AI_STRATEGIST_PROVIDER=openai` + `AI_STRATEGIST_ENDPOINT=https://openrouter.ai/api/v1/chat/completions` is the canonical strategist runtime path
    - `OPENROUTER_MODEL_REPORTER_FINAL=openrouter/auto` and `OPENROUTER_MODEL_DAILY_REPORT=openrouter/auto` let end-of-day reporter summaries use the full routed pool
    - `OPENROUTER_MODEL_OPERATOR_UI=openrouter/free` and `OPENROUTER_MODEL_REPORTER_INTRADAY=openrouter/free` keep frequent intraday/operator briefs on the free-model pool
    - `OPENROUTER_DEFAULT_MODEL=openrouter/free` remains the generic low-cost fallback for simple LLM requests
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
  - reporter also appends compact feedback records to `data/strategy_memory/feedback.jsonl`
  - reporter also refreshes `data/strategy_memory/daily/YYYY-MM-DD.json` so repeated closeout runs do not inflate Strategist memory
  - reporter AI review can now link findings back to deterministic evidence via:
    - `ai_evidence_catalog`
    - `ai_findings_detailed`
    - `ai_root_causes_detailed`
    - `ai_improvement_suggestions_detailed`
  - if AI review returns `status=ok` but empty lists, reporter enriches the output from deterministic evidence so downstream strategy memory stays usable

## Off-Hours Validation Loop

- Purpose:
  - keep validating the integrated chain outside market hours when broker-side mock investor trading cannot run
  - simulate local fills/state transitions so strategy/scanner/monitor/report quality can still be evaluated
- Canonical entry points:
  - direct loop: `scripts/run_offhours_validation_loop.py`
  - orchestration phase: `scripts/run_mock_exam_day.py --phase session --allow-offhours-simulated-session`
- Runtime contract:
  - forces `EXECUTION_MODE=mock`
  - forces `ALLOW_REAL_EXECUTION=false`
  - optionally isolates state with `STATE_STORE_PATH` / `--state-path`
  - uses shared `EVENT_LOG_PATH` / `--event-log-path` for unified observability
- Pipeline shape:
  1. load persisted state
  2. inject local mock portfolio/price readers
  3. run Strategist -> Scanner -> Monitor -> Supervisor/Executor-compatible decision path
  4. apply local mock fills into persisted state
  5. save state for next off-hours cycle
- What it validates well:
  - strategist framing quality
  - scanner candidate/selection behavior
  - monitor entry/exit logic against persisted positions
  - decision trace / evidence / operator report generation
- What it does not validate:
  - broker-side market-session rules
  - exchange session behavior
  - real/mock broker order acceptance during closed market

## Off-Hours Full Trace Bundle

- Purpose:
  - run one off-hours cycle and emit one complete explainability bundle
  - useful when operators want a single full data packet instead of a continuous loop
- Entry point:
  - `scripts/run_offhours_full_trace_bundle.py`
- Output intent:
  - what news/global sentiment was collected
  - what LLM prompt/response Strategist used
  - what Kiwoom-source candidate mix Scanner used
  - what numeric score/feature snapshot selected the Top-1 stock
  - what Monitor threshold/policy drove entry or exit
  - what Reporter suggested for next-run learning
- Default artifact tree:
  - `reports/dev/analysis/offhours_full_trace/offhours_full_trace_<run>.md|json`
  - `reports/dev/analysis/offhours_full_trace/agent_pipeline_trace/*`
  - `reports/dev/analysis/offhours_full_trace/trade_explain/*`
  - `reports/dev/analysis/offhours_full_trace/reporter_analysis/*`
