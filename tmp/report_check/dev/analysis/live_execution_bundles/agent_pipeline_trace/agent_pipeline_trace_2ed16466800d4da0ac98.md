# Agent Pipeline Trace (2ed16466800d4da0ac9849a7e509328a)

- day: **2026-03-18**
- event_log_path: `data\logs\events.jsonl`
- evidence_log_path: `data\evidence_ledger\events.jsonl`

## Commander
- mode: **integrated_chain**
- agents: `["commander_router", "strategist", "scanner", "monitor", "decision", "supervisor", "executor", "reporter"]`
- route_ts: `2026-03-18T01:23:51+00:00`
- end_status: **ok**

## Strategist
- news_source: **naver** headlines=59 symbols=12
- news_query_targets: `["코스피", "코스닥", "미국 증시", "증시 전망", "거시경제", "하락 종목 수", "약세 업종"]`
- news_query_reasoning: global_score=-0.01 macro_risk=0.00 index_trend=0.00 vix=22.37 vix_pressure=0.119; explicit_targets_first=코스피, 코스닥, 미국 증시, 증시 전망; neutral context kept broad market and macro queries; weak breadth added 하락 종목 수/약세 업종 queries
- global_sentiment: score=-0.0078 status=ok source=yfinance
- global_index_moves: `{"sp500_pct": 0.24942548757938, "nasdaq_pct": 0.47084477608292374, "dow_pct": 0.0997979661151227}`
- fear_index: `{"provider": "yfinance", "ticker": "^VIX", "level": 22.3700008392334, "change_pct": -4.848997782007491, "neutral_level": 20.0, "level_pressure": 0.11850004196166992}`
- macro_stress: active=False flags=`[]` reason=`None`
- llm: provider=openrouter model=openrouter/free ok=False latency_ms=7072
- llm_prompt_captured: **True**
- llm_response_captured: **True**
- themes: `["broad_market_leaders"]`
- playbook: **defensive**
- scanner_source_policy: `{"preferred_sources": ["top_value", "top_volume", "sector_theme", "operator_watchlist"], "include_top_value": true, "include_top_volume": true, "include_change_rate": false, "include_condition_search": false, "include_sector_candidates": true, "include_watchlist": true, "top_candidate_pool": 18, "condition_limit": 0, "source_weights": {"top_value": 2.2, "top_volume": 1.9, "condition_search": 0.0, "sector_theme": 1.8, "operator_watchlist": 1.1, "top_change_rate": 0.0}, "reason": "defensive frame prioritizes liquid leaders and suppresses fast-mover sources"}`
- news_sample_titles: `["NewsItem(title=\"BTS 완전체 복귀에 K엔터주 다시 '관심' [BTS 이코노미]\", url='https://www.econovill.com/news/articleView.html?idxno=732170'", "삼성자산운용, 삼성전자채권혼합 ETF 순자산 1조 돌파", "게임주 대상 공매도 견제 거세졌다", "[N2 특징주] 비츠로셀 장중 상한가…美 군용 드론 배터리 협력 기대", "거래소, 관리종목 해제 번복에 주가 급등락…투자자 피해 어쩌나"]`

## Scanner
- candidate_source: **kiwoom_market_data**
- pool: before=5 after=5
- kiwoom_source_mix: `{"top_value": 18, "top_volume": 18, "top_change_rate": 0, "condition_search": 0, "sector_theme": 5, "operator_watchlist": 0}`
- condition_search: status=disabled source=disabled reason=condition_search_baseline_disabled
- scanner_source_policy: `{"include_top_value": true, "include_top_volume": true, "include_change_rate": false, "include_condition_search": false, "include_sector_candidates": true, "include_watchlist": true, "top_candidate_pool": 18, "condition_limit": 0, "preferred_sources": ["top_value", "top_volume", "sector_theme", "operator_watchlist"], "source_weights": {"top_value": 2.2, "top_volume": 1.9, "condition_search": 0.0, "sector_theme": 1.8, "operator_watchlist": 1.1, "top_change_rate": 0.0}, "reason": "defensive frame prioritizes liquid leaders and suppresses fast-mover sources"}`
- top_stock: **000660** top_score=1.237159295190661
- top_ranked_symbols: `["000660", "005930", "032820", "069500", "122630"]`
- score_breakdown_summary: `{"trading_value": 0.23760000000000003, "momentum": 0.22, "trend": 0.044738817112584116, "ma_alignment": 0.03402, "adx_trend": 0.0, "volume_surge": 0.0, "intraday_strength": 0.036, "vwap_alignment": 0.036, "theme_boost": 0.0648, "sentiment": 0.020408157547311016, "cross_section_rank": 0.05, "avoid_theme_penalty": -0.0, "repeat_symbol_penalty": -0.33999999999999997, "risk_penalty": -0.08665014241821518, "rank_bonus": 0.007050359712230217}`
- selected_candidate: `{"symbol": "000660", "why": "top_value+sector_theme", "sources": ["top_value", "sector_theme"], "source_scores": {"top_value": 2.18, "sector_theme": 1.74}, "rank_score": 0.7050359712230216, "universe_score": 3.92, "score_total": 1.237159295190661, "risk_score": 0.48644116260457426, "confidence": 0.8184189106931306, "score_breakdown": {"trading_value": 0.23760000000000003, "momentum": 0.22, "trend": 0.044738817112584116, "ma_alignment": 0.03402, "adx_trend": 0.0, "volume_surge": 0.0, "intraday_strength": 0.036, "vwap_alignment": 0.036, "theme_boost": 0.0648, "sentiment": 0.020408157547311016, "cross_section_rank": 0.05, "avoid_theme_penalty": -0.0, "repeat_symbol_penalty": -0.33999999999999997, "risk_penalty": -0.08665014241821518, "rank_bonus": 0.007050359712230217}, "feature_snapshot": {"quote_trading_value": 0.0, "quote_volume": 0.0, "intraday_change_pct": 0.0, "skill_quote_price": null, "engine_ma20_gap": 0.052935684090262836, "engine_ma60": null, "engine_ma120": null, "engine_adx14": 11.027589622000113, "engine_trend_strength": 0.11027589622000113, "engine_volume_spike20": 0.04212608953301986, "engine_volatility20": 0.06322326557023951, "engine_vwap_distance": 0.20657727537709136, "engine_sector_relative_strength": 0.0, "engine_cross_section_rank": 1.0, "engine_regime": "high_volatility", "engine_signal_score": 0.0}, "component_snapshot": {"news_sentiment": 0.48926124231742707, "global_sentiment": -0.007823035001162194, "trading_value_component": 1.0, "momentum_component": 1.0, "trend_component": 0.20712415329900052, "volume_surge_component": 0.0, "intraday_strength_component": 0.3, "theme_boost_component": 1.0, "sentiment_component": 0.3401359591218503, "volatility_penalty_component": 0.6644653114047901, "gap_penalty_component": 0.013254786450661185, "avoid_theme_penalty_component": 0.0}}`

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
- `python scripts/run_agent_pipeline_trace_report.py --run-id 2ed16466800d4da0ac9849a7e509328a --json`
- `python scripts/query_trade_reason_chain.py --run-id 2ed16466800d4da0ac9849a7e509328a --only-broker-success`