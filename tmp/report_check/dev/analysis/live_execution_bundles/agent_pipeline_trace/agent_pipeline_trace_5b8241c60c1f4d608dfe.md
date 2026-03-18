# Agent Pipeline Trace (5b8241c60c1f4d608dfe65d658aca9b3)

- day: **2026-03-18**
- event_log_path: `data\logs\events.jsonl`
- evidence_log_path: `data\evidence_ledger\events.jsonl`

## Commander
- mode: **integrated_chain**
- agents: `["commander_router", "strategist", "scanner", "monitor", "decision", "supervisor", "executor", "reporter"]`
- route_ts: `2026-03-18T03:30:21+00:00`
- end_status: **ok**

## Strategist
- news_source: **none** headlines=0 symbols=0
- global_sentiment: score=0.0000 status= source=
- llm: provider= model= ok=False latency_ms=0
- llm_prompt_captured: **False**
- llm_response_captured: **False**
- themes: `[]`
- playbook: ****

## Scanner
- candidate_source: **kiwoom_market_data**
- pool: before=5 after=5
- kiwoom_source_mix: `{"top_value": 18, "top_volume": 18, "top_change_rate": 0, "condition_search": 0, "sector_theme": 5, "operator_watchlist": 0}`
- condition_search: status=disabled source=disabled reason=condition_search_baseline_disabled
- scanner_source_policy: `{"include_top_value": true, "include_top_volume": true, "include_change_rate": false, "include_condition_search": false, "include_sector_candidates": true, "include_watchlist": true, "top_candidate_pool": 18, "condition_limit": 0, "preferred_sources": ["top_value", "top_volume", "sector_theme", "operator_watchlist"], "source_weights": {"top_value": 2.2, "top_volume": 1.9, "condition_search": 0.0, "sector_theme": 1.8, "operator_watchlist": 1.1, "top_change_rate": 0.0}, "reason": "defensive frame prioritizes liquid leaders and suppresses fast-mover sources"}`
- top_stock: **005930** top_score=1.2350220156617235
- top_ranked_symbols: `["005930", "032820", "000660", "047040", "122630"]`
- score_breakdown_summary: `{"trading_value": 0.2613600000000001, "momentum": 0.209, "trend": 0.03955715971675847, "ma_alignment": 0.03465, "adx_trend": 0.0, "volume_surge": 0.0, "intraday_strength": 0.034199999999999994, "vwap_alignment": 0.034199999999999994, "theme_boost": 0.06, "sentiment": 0.0, "cross_section_rank": 0.05, "avoid_theme_penalty": -0.0, "repeat_symbol_penalty": -0.06, "risk_penalty": -0.0960676123308003, "rank_bonus": 0.006923076923076923}`
- selected_candidate: `{"symbol": "005930", "why": "top_value+sector_theme", "sources": ["top_value", "sector_theme"], "source_scores": {"top_value": 2.2, "sector_theme": 1.76}, "rank_score": 0.6923076923076923, "universe_score": 3.96, "score_total": 1.2350220156617235, "risk_score": 0.532709038124032, "confidence": 0.8397262013386629, "score_breakdown": {"trading_value": 0.2613600000000001, "momentum": 0.209, "trend": 0.03955715971675847, "ma_alignment": 0.03465, "adx_trend": 0.0, "volume_surge": 0.0, "intraday_strength": 0.034199999999999994, "vwap_alignment": 0.034199999999999994, "theme_boost": 0.06, "sentiment": 0.0, "cross_section_rank": 0.05, "avoid_theme_penalty": -0.0, "repeat_symbol_penalty": -0.06, "risk_penalty": -0.0960676123308003, "rank_bonus": 0.006923076923076923}, "feature_snapshot": {"quote_trading_value": 0.0, "quote_volume": 0.0, "intraday_change_pct": 0.0, "skill_quote_price": null, "engine_ma20_gap": 0.06253084976489243, "engine_ma60": null, "engine_ma120": null, "engine_adx14": 4.956726986624709, "engine_trend_strength": 0.049567269866247085, "engine_volume_spike20": 0.419036180757216, "engine_volatility20": 0.05613841192277201, "engine_vwap_distance": 0.2567021979906259, "engine_sector_relative_strength": -0.010520599798313768, "engine_cross_section_rank": 1.0, "engine_regime": "high_volatility", "engine_signal_score": 0.5}, "component_snapshot": {"news_sentiment": 0.0, "global_sentiment": -0.009090701857732105, "trading_value_component": 1.0, "momentum_component": 1.0, "trend_component": 0.17980527143981118, "volume_surge_component": 0.0, "intraday_strength_component": 0.3, "theme_boost_component": 1.0, "sentiment_component": 0.0, "volatility_penalty_component": 0.5227682384554402, "gap_penalty_component": 0.057688057172326175, "avoid_theme_penalty_component": 0.0}}`

## Monitor
- selected_symbol: **005930**
- entry_reason=no_position exit_reason=no_position monitor_reason=no_position
- position_age_seconds=None min_hold_blocked=False sell_cooldown_blocked=False
- thresholds: `{"hard_stop_pct": 0.01, "stop_loss_pct": 0.05333149132663341, "take_profit_pct": 0.005939899776, "max_hold_sec": 0, "time_stop_sec": 0, "trailing_stop_pct": 0.026665745663316705, "vol_expansion_ratio": 1.6, "news_shock_threshold": 0.0, "peak_drawdown_exit_pct": 0.0033120000000000003, "vwap_breakdown_pct": 0.005, "intraday_low_break_pct": 0.002, "trend_strength_floor": -0.15, "eod_flat_cutoff_min": 10}` min_hold=600 sell_cooldown=300 confirm_ticks=3
- strategy_frame_adjustments: `["monitor_guidance:defensive_exit", "risk_tone:conservative", "trade_aggressiveness:low"]`

## Supervisor
- verdict=approve allow=True reason=Allowed

## Executor
- execution_attempted=True ok=True broker_code=0
- execution_mode=real kiwoom_mode=mock broker_env=mock effective_mode=mock_broker_http
- api_id=ORDER_SUBMIT url=https://mockapi.kiwoom.com/api/dostk/ordr action=BUY symbol=005930 qty=1

## Reporter
- in_run_trace_available: **False**
- reporter_analysis_day_file_found: **True**
- reporter_analysis_found: **True**
- reporter_analysis_path: `tmp\report_check\dev\analysis\reporter_analysis\reporter_analysis_2026-03-18.json`

## Next Command
- `python scripts/run_agent_pipeline_trace_report.py --run-id 5b8241c60c1f4d608dfe65d658aca9b3 --json`
- `python scripts/query_trade_reason_chain.py --run-id 5b8241c60c1f4d608dfe65d658aca9b3 --only-broker-success`