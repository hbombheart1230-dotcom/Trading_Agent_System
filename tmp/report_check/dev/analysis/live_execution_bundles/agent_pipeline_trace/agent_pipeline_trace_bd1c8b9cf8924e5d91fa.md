# Agent Pipeline Trace (bd1c8b9cf8924e5d91fa118dd361f9e6)

- day: **2026-03-18**
- event_log_path: `data\logs\events.jsonl`
- evidence_log_path: `data\evidence_ledger\events.jsonl`

## Commander
- mode: **integrated_chain**
- agents: `["commander_router", "strategist", "scanner", "monitor", "decision", "supervisor", "executor", "reporter"]`
- route_ts: `2026-03-18T04:10:30+00:00`
- end_status: **ok**

## Strategist
- news_source: **naver** headlines=60 symbols=12
- news_query_targets: `["코스피", "코스닥", "미국 증시", "증시 전망", "거시경제", "하락 종목 수", "약세 업종"]`
- news_query_reasoning: global_score=-0.01 macro_risk=0.00 index_trend=0.00 vix=22.37 vix_pressure=0.119; explicit_targets_first=코스피, 코스닥, 미국 증시, 증시 전망; neutral context kept broad market and macro queries; weak breadth added 하락 종목 수/약세 업종 queries
- global_sentiment: score=-0.0091 status=ok source=yfinance
- global_index_moves: `{"sp500_pct": 0.24942548757938, "nasdaq_pct": 0.47084477608292374, "dow_pct": 0.0997979661151227}`
- fear_index: `{"provider": "yfinance", "ticker": "^VIX", "level": 22.3700008392334, "change_pct": -4.848997782007491, "neutral_level": 20.0, "level_pressure": 0.11850004196166992}`
- macro_stress: active=False flags=`[]` reason=`None`
- llm: provider=openrouter model=openrouter/free ok=False latency_ms=16596
- llm_prompt_captured: **True**
- llm_response_captured: **True**
- themes: `["broad_market_leaders"]`
- playbook: **defensive**
- scanner_source_policy: `{"preferred_sources": ["top_value", "top_volume", "sector_theme", "operator_watchlist"], "include_top_value": true, "include_top_volume": true, "include_change_rate": false, "include_condition_search": false, "include_sector_candidates": true, "include_watchlist": true, "top_candidate_pool": 18, "condition_limit": 0, "source_weights": {"top_value": 2.2, "top_volume": 1.9, "condition_search": 0.0, "sector_theme": 1.8, "operator_watchlist": 1.1, "top_change_rate": 0.0}, "reason": "defensive frame prioritizes liquid leaders and suppresses fast-mover sources"}`
- news_sample_titles: `["지누스 주주 노경열, 지누스 주식등의 수 1만6215주 증가…총 지분율 5%", "큐리옥스바이오시스템즈 주가 28% 도약…장중 상한가 도달하기도", "NewsItem(title=\"<b>코스피</b> 사흘째 상승…'20만전자·100만닉스'\", url='https://n.news.naver.com/mnews/article/422/0000845338?sid=101', ", "[진단_자율주행 ⑦팅크웨어] 사업 다각화에도 수익성 후퇴, 지배주주 중...", "큐리옥스바이오시스템즈 주가 28% 도약…장중 상한가 도달하기도"]`

## Scanner
- candidate_source: **kiwoom_market_data**
- pool: before=5 after=5
- kiwoom_source_mix: `{"top_value": 0, "top_volume": 18, "top_change_rate": 0, "condition_search": 0, "sector_theme": 5, "operator_watchlist": 0}`
- condition_search: status=disabled source=disabled reason=condition_search_baseline_disabled
- scanner_source_policy: `{"include_top_value": true, "include_top_volume": true, "include_change_rate": false, "include_condition_search": false, "include_sector_candidates": true, "include_watchlist": true, "top_candidate_pool": 18, "condition_limit": 0, "preferred_sources": ["top_value", "top_volume", "sector_theme", "operator_watchlist"], "source_weights": {"top_value": 2.2, "top_volume": 1.9, "condition_search": 0.0, "sector_theme": 1.8, "operator_watchlist": 1.1, "top_change_rate": 0.0}, "reason": "defensive frame prioritizes liquid leaders and suppresses fast-mover sources"}`
- top_stock: **000660** top_score=1.1191666738952444
- top_ranked_symbols: `["000660", "047040", "032820", "005930", "122630"]`
- score_breakdown_summary: `{"trading_value": 0.0, "momentum": 0.22, "trend": 0.06848292134831466, "ma_alignment": 0.03402, "adx_trend": 0.01371235955056182, "volume_surge": 0.0, "intraday_strength": 0.113952, "vwap_alignment": 0.036, "theme_boost": 0.0648, "sentiment": 0.004859208453898524, "cross_section_rank": 0.025, "avoid_theme_penalty": -0.0, "repeat_symbol_penalty": -0.12, "risk_penalty": -0.12573215364625145, "rank_bonus": 0.0050279329608938555}`
- selected_candidate: `{"symbol": "000660", "why": "sector_theme", "sources": ["sector_theme"], "source_scores": {"sector_theme": 1.8}, "rank_score": 0.5027932960893855, "universe_score": 1.8, "score_total": 1.1191666738952444, "risk_score": 0.5287867008988767, "confidence": 0.7731490893511479, "score_breakdown": {"trading_value": 0.0, "momentum": 0.22, "trend": 0.06848292134831466, "ma_alignment": 0.03402, "adx_trend": 0.01371235955056182, "volume_surge": 0.0, "intraday_strength": 0.113952, "vwap_alignment": 0.036, "theme_boost": 0.0648, "sentiment": 0.004859208453898524, "cross_section_rank": 0.025, "avoid_theme_penalty": -0.0, "repeat_symbol_penalty": -0.12, "risk_penalty": -0.12573215364625145, "rank_bonus": 0.0050279329608938555}, "feature_snapshot": {"quote_trading_value": 1913949218000.0, "quote_volume": 1902436.0, "intraday_change_pct": 4.64, "skill_quote_price": 1015000.0, "engine_ma20_gap": 0.05960249345215085, "engine_ma60": null, "engine_ma120": null, "engine_adx14": 21.34831460674158, "engine_trend_strength": 0.2134831460674158, "engine_volume_spike20": 2.2404449559529644e-07, "engine_volatility20": 0.06328111554590507, "engine_vwap_distance": 0.22192756233691924, "engine_sector_relative_strength": 0.0, "engine_cross_section_rank": 0.5, "engine_regime": "high_volatility", "engine_signal_score": 0.0}, "component_snapshot": {"news_sentiment": 0.11959306525898167, "global_sentiment": -0.009094460387705826, "trading_value_component": 0.0, "momentum_component": 1.0, "trend_component": 0.317050561797753, "volume_surge_component": 0.0, "intraday_strength_component": 0.9496, "theme_boost_component": 1.0, "sentiment_component": 0.08098680756497541, "volatility_penalty_component": 0.6656223109181014, "gap_penalty_component": 0.0, "avoid_theme_penalty_component": 0.0}}`

## Monitor
- selected_symbol: **000660**
- entry_reason=no_position exit_reason=no_position monitor_reason=no_position
- position_age_seconds=None min_hold_blocked=False sell_cooldown_blocked=False
- thresholds: `{"hard_stop_pct": 0.01, "stop_loss_pct": 0.08, "take_profit_pct": 0.006855840000000001, "max_hold_sec": 0, "time_stop_sec": 0, "trailing_stop_pct": 0.04, "vol_expansion_ratio": 1.6, "news_shock_threshold": 0.0, "peak_drawdown_exit_pct": 0.00368, "vwap_breakdown_pct": 0.005, "intraday_low_break_pct": 0.002, "trend_strength_floor": -0.15, "eod_flat_cutoff_min": 10}` min_hold=360 sell_cooldown=300 confirm_ticks=1
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
- reporter_analysis_found: **False**
- reporter_analysis_path: `tmp\report_check\dev\analysis\reporter_analysis\reporter_analysis_2026-03-18.json`

## Next Command
- `python scripts/run_agent_pipeline_trace_report.py --run-id bd1c8b9cf8924e5d91fa118dd361f9e6 --json`
- `python scripts/query_trade_reason_chain.py --run-id bd1c8b9cf8924e5d91fa118dd361f9e6 --only-broker-success`