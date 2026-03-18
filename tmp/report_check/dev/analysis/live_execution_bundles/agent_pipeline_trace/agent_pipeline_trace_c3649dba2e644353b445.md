# Agent Pipeline Trace (c3649dba2e644353b445e7a1396b0329)

- day: **2026-03-18**
- event_log_path: `data\logs\events.jsonl`
- evidence_log_path: `data\evidence_ledger\events.jsonl`

## Commander
- mode: **integrated_chain**
- agents: `["commander_router", "strategist", "scanner", "monitor", "decision", "supervisor", "executor", "reporter"]`
- route_ts: `2026-03-18T02:36:19+00:00`
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
- top_stock: **000660** top_score=1.2438735224557955
- top_ranked_symbols: `["000660", "005930", "032820", "069500", "122630"]`
- score_breakdown_summary: `{"trading_value": 0.23760000000000003, "momentum": 0.22, "trend": 0.044738817112584116, "ma_alignment": 0.03402, "adx_trend": 0.0, "volume_surge": 0.0, "intraday_strength": 0.036, "vwap_alignment": 0.036, "theme_boost": 0.0648, "sentiment": 0.011254679903919292, "cross_section_rank": 0.05, "avoid_theme_penalty": -0.0, "repeat_symbol_penalty": -0.28, "risk_penalty": -0.08665014241821518, "rank_bonus": 0.00697508896797153}`
- selected_candidate: `{"symbol": "000660", "why": "top_value+sector_theme", "sources": ["top_value", "sector_theme"], "source_scores": {"top_value": 2.18, "sector_theme": 1.74}, "rank_score": 0.697508896797153, "universe_score": 3.92, "score_total": 1.2438735224557955, "risk_score": 0.4716849180550704, "confidence": 0.8301072648376853, "score_breakdown": {"trading_value": 0.23760000000000003, "momentum": 0.22, "trend": 0.044738817112584116, "ma_alignment": 0.03402, "adx_trend": 0.0, "volume_surge": 0.0, "intraday_strength": 0.036, "vwap_alignment": 0.036, "theme_boost": 0.0648, "sentiment": 0.011254679903919292, "cross_section_rank": 0.05, "avoid_theme_penalty": -0.0, "repeat_symbol_penalty": -0.28, "risk_penalty": -0.08665014241821518, "rank_bonus": 0.00697508896797153}, "feature_snapshot": {"quote_trading_value": 0.0, "quote_volume": 0.0, "intraday_change_pct": 0.0, "skill_quote_price": null, "engine_ma20_gap": 0.052935684090262836, "engine_ma60": null, "engine_ma120": null, "engine_adx14": 11.027589622000113, "engine_trend_strength": 0.11027589622000113, "engine_volume_spike20": 0.04212608953301986, "engine_volatility20": 0.06322326557023951, "engine_vwap_distance": 0.20657727537709136, "engine_sector_relative_strength": 0.0, "engine_cross_section_rank": 1.0, "engine_regime": "high_volatility", "engine_signal_score": 0.0}, "component_snapshot": {"news_sentiment": 0.2718436315353539, "global_sentiment": -0.009041812253642754, "trading_value_component": 1.0, "momentum_component": 1.0, "trend_component": 0.20712415329900052, "volume_surge_component": 0.0, "intraday_strength_component": 0.3, "theme_boost_component": 1.0, "sentiment_component": 0.18757799839865488, "volatility_penalty_component": 0.6644653114047901, "gap_penalty_component": 0.013254786450661185, "avoid_theme_penalty_component": 0.0}}`

## Monitor
- selected_symbol: **000660**
- entry_reason=no_position exit_reason=no_position monitor_reason=no_position
- position_age_seconds=None min_hold_blocked=False sell_cooldown_blocked=False
- thresholds: `{"hard_stop_pct": 0.01, "stop_loss_pct": 0.06006210229172753, "take_profit_pct": 0.006855840000000001, "max_hold_sec": 0, "time_stop_sec": 0, "trailing_stop_pct": 0.030031051145863765, "vol_expansion_ratio": 1.6, "news_shock_threshold": 0.0, "peak_drawdown_exit_pct": 0.00368, "vwap_breakdown_pct": 0.005, "intraday_low_break_pct": 0.002, "trend_strength_floor": -0.15, "eod_flat_cutoff_min": 10}` min_hold=360 sell_cooldown=300 confirm_ticks=1
- strategy_frame_adjustments: `["monitor_guidance:defensive_exit"]`

## Supervisor
- verdict=approve allow=True reason=Allowed

## Executor
- execution_attempted=True ok=True broker_code=0
- execution_mode=real kiwoom_mode=mock broker_env=mock effective_mode=mock_broker_http
- api_id=ORDER_SUBMIT url=https://mockapi.kiwoom.com/api/dostk/ordr action=BUY symbol=000660 qty=1

## Reporter
- in_run_trace_available: **False**
- reporter_analysis_day_file_found: **True**
- reporter_analysis_found: **True**
- reporter_analysis_path: `tmp\report_check\dev\analysis\reporter_analysis\reporter_analysis_2026-03-18.json`

## Next Command
- `python scripts/run_agent_pipeline_trace_report.py --run-id c3649dba2e644353b445e7a1396b0329 --json`
- `python scripts/query_trade_reason_chain.py --run-id c3649dba2e644353b445e7a1396b0329 --only-broker-success`