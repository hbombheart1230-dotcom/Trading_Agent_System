# Agent Pipeline Trace (run_trace_1)

- day: **2026-03-10**
- event_log_path: `C:\Trading_Agent_System\.pytest-phase522-runnerup\test_agent_pipeline_trace_repo2\events.jsonl`
- evidence_log_path: `C:\Trading_Agent_System\.pytest-phase522-runnerup\test_agent_pipeline_trace_repo2\evidence.jsonl`

## Commander
- mode: **integrated_chain**
- agents: `[]`
- route_ts: `2026-03-10T00:00:00+00:00`
- end_status: ****

## Strategist
- news_source: **none** headlines=0 symbols=0
- global_sentiment: score=0.0000 status= source=
- llm: provider= model= ok=False latency_ms=0
- llm_prompt_captured: **False**
- llm_response_captured: **False**
- themes: `[]`
- playbook: ****

## News -> Symbol Linkage
- linkage_strength: **weak**
- summary: Strategist queried 0 news targets and linked selected symbol - to 0 candidate headlines.

## Scanner
- candidate_source: ****
- pool: before=0 after=0
- kiwoom_source_mix: `{}`
- top_stock: **** top_score=None
- top_ranked_symbols: `[]`
- score_breakdown_summary: `{}`

## Monitor
- selected_symbol: ****
- entry_reason= exit_reason= monitor_reason=
- position_age_seconds=None min_hold_blocked=False sell_cooldown_blocked=False
- thresholds: `{}` min_hold=0 sell_cooldown=0 confirm_ticks=0

## Reasoning Trace
- commander_summary: -
- strategist_summary: -
- scanner_summary: -
- monitor_summary: -
- provenance: shadow_used=False strategist_fallback_used=False

## Supervisor
- verdict= allow=None reason=

## Executor
- execution_attempted=False ok=False broker_code=
- execution_mode= kiwoom_mode= broker_env= effective_mode=
- api_id= url= action= symbol= qty=None

## Reporter
- in_run_trace_available: **False**
- reporter_analysis_day_file_found: **True**
- reporter_analysis_found: **False**
- reporter_analysis_path: `C:\Trading_Agent_System\.pytest-phase522-runnerup\test_agent_pipeline_trace_repo2\reports\reporter_analysis\reporter_analysis_2026-03-10.json`

## Next Command
- `python scripts/run_agent_pipeline_trace_report.py --run-id run_trace_1 --json`
- `python scripts/query_trade_reason_chain.py --run-id run_trace_1 --only-broker-success`