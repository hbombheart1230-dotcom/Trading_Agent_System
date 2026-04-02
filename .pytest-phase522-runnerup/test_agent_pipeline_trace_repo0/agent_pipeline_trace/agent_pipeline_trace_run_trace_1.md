# Agent Pipeline Trace (run_trace_1)

- day: **2026-03-10**
- event_log_path: `C:\Trading_Agent_System\.pytest-phase522-runnerup\test_agent_pipeline_trace_repo0\events.jsonl`
- evidence_log_path: `C:\Trading_Agent_System\.pytest-phase522-runnerup\test_agent_pipeline_trace_repo0\evidence.jsonl`

## Commander
- mode: **integrated_chain**
- agents: `["strategist", "scanner", "monitor", "supervisor", "executor", "reporter"]`
- route_ts: `2026-03-10T00:00:00+00:00`
- end_status: **ok**

## Strategist
- news_source: **naver** headlines=2 symbols=1
- news_query_targets: `["반도체", "코스피", "AI"]`
- news_query_reasoning: risk-on context added leader/risk-appetite market queries; theme hints expanded queries from semiconductor, AI
- global_sentiment: score=0.1200 status=ok source=yfinance
- global_index_moves: `{"sp500_pct": 1.2, "nasdaq_pct": 1.8, "dow_pct": 0.7}`
- fear_index: `{"level": 27.1, "level_pressure": 0.355, "change_pct": -1.2}`
- macro_stress: active=True flags=`["elevated_vix", "dollar_strength"]` reason=`vix=27.10 pressure=0.355 dxy_pct=0.31 tnx_delta=0.0040`
- llm: provider=openrouter model=minimax/minimax-m2.5 ok=True latency_ms=420
- llm_prompt_captured: **True**
- llm_response_captured: **True**
- themes: `["semiconductor", "AI"]`
- playbook: **breakout**
- scanner_source_policy: `{"preferred_sources": ["top_change_rate", "condition_search", "top_volume"], "include_change_rate": true, "include_condition_search": true}`
- news_sample_titles: `["삼성전자 반등"]`

## News -> Symbol Linkage
- linkage_strength: **strong**
- summary: Strategist queried 3 news targets and linked selected symbol 005930 to 1 candidate headlines. 005930 remained inside strategist candidate hints.
- candidate_symbols_hint: `["005930", "000660"]`
- linkage_news_query_targets: `["반도체", "코스피", "AI"]`
- selected_symbol_linkage: symbol=005930 in_candidate_hints=True
- runner_up_symbol_linkage: symbol=000660 in_candidate_hints=True
- selected_symbol_headlines: `["삼성전자 HBM 수요 기대감 확대"]`
- runner_up_symbol_headlines: `["하이닉스 AI 서버 수요 지속"]`
- selected_vs_runner_up: Selected 005930 vs runner-up 000660: headlines 1 vs 1, hint_match true vs true.
- linkage_market_headlines: `["코스피 반도체 강세 지속"]`

## Scanner
- candidate_source: **kiwoom_market_data**
- pool: before=10 after=6
- kiwoom_source_mix: `{"top_value": 1, "top_volume": 1, "top_change_rate": 1}`
- condition_search: status=unavailable source=unavailable reason=kiwoom_condition_websocket_not_integrated
- scanner_source_policy: `{"preferred_sources": ["top_change_rate", "condition_search", "top_volume"], "include_change_rate": true, "include_condition_search": true}`
- top_stock: **005930** top_score=0.87
- top_ranked_symbols: `["005930", "000660"]`
- score_breakdown_summary: `{"momentum": 0.24, "trend": 0.2}`
- selected_candidate: `{"symbol": "005930", "sources": ["top_value", "top_volume"], "feature_snapshot": {"quote_trading_value": 1000000.0}}`

## Monitor
- selected_symbol: **005930**
- entry_reason=breakout_confirmation exit_reason= monitor_reason=hold
- position_age_seconds=120 min_hold_blocked=False sell_cooldown_blocked=False
- thresholds: `{"stop_loss_pct": 0.03}` min_hold=600 sell_cooldown=300 confirm_ticks=2

## Reasoning Trace
- commander_summary: Commander kept the day in measured risk mode.
- strategist_summary: risk-on context added leader/risk-appetite market queries; theme hints expanded queries from semiconductor, AI
- scanner_summary: Scanner selected 005930 after strategist-guided weighting.
- monitor_summary: Monitor held because breakout confirmation remains valid.
- provenance: shadow_used=True strategist_fallback_used=False

## Supervisor
- verdict=APPROVE allow=True reason=ok

## Executor
- execution_attempted=True ok=True broker_code=0
- execution_mode=real kiwoom_mode=mock broker_env=mock effective_mode=mock_broker_http
- api_id=TTTC0802U url=https://mock-api.example/orders action=BUY symbol=005930 qty=1

## Reporter
- in_run_trace_available: **True**
- reporter_analysis_day_file_found: **True**
- reporter_analysis_found: **True**
- reporter_analysis_path: `C:\Trading_Agent_System\.pytest-phase522-runnerup\test_agent_pipeline_trace_repo0\reports\reporter_analysis\reporter_analysis_2026-03-10.json`

## Next Command
- `python scripts/run_agent_pipeline_trace_report.py --run-id run_trace_1 --json`
- `python scripts/query_trade_reason_chain.py --run-id run_trace_1 --only-broker-success`