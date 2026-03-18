# Agent Pipeline Trace (ec2c700d34564245903c51ccf6d606d8)

- day: **2026-03-18**
- event_log_path: `data\logs\events.jsonl`
- evidence_log_path: `data\evidence_ledger\events.jsonl`

## Commander
- mode: **integrated_chain**
- agents: `["commander_router", "strategist", "scanner", "monitor", "decision", "supervisor", "executor", "reporter"]`
- route_ts: `2026-03-18T03:55:06+00:00`
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
- candidate_source: ****
- pool: before=0 after=0
- kiwoom_source_mix: `{}`
- top_stock: **** top_score=None
- top_ranked_symbols: `[]`
- score_breakdown_summary: `{}`

## Monitor
- selected_symbol: **005930**
- entry_reason=peak_drawdown exit_reason=peak_drawdown monitor_reason=confirmed_exit_signal
- position_age_seconds=1482 min_hold_blocked=False sell_cooldown_blocked=False
- thresholds: `{"hard_stop_pct": 0.01, "stop_loss_pct": 0.08, "take_profit_pct": 0.005939899776, "max_hold_sec": 0, "time_stop_sec": 0, "trailing_stop_pct": 0.04, "vol_expansion_ratio": 1.6, "news_shock_threshold": 0.0, "peak_drawdown_exit_pct": 0.0033120000000000003, "vwap_breakdown_pct": 0.005, "intraday_low_break_pct": 0.002, "trend_strength_floor": -0.15, "eod_flat_cutoff_min": 10, "effective_stop_loss_pct": 0.01, "effective_stop_reason": "hard_stop"}` min_hold=600 sell_cooldown=300 confirm_ticks=3
- strategy_frame_adjustments: `["monitor_guidance:defensive_exit", "risk_tone:conservative", "trade_aggressiveness:low"]`

## Supervisor
- verdict=approve allow=True reason=Allowed

## Executor
- execution_attempted=True ok=True broker_code=0
- execution_mode=real kiwoom_mode=mock broker_env=mock effective_mode=mock_broker_http
- api_id=ORDER_SUBMIT url=https://mockapi.kiwoom.com/api/dostk/ordr action=SELL symbol=005930 qty=1

## Reporter
- in_run_trace_available: **False**
- reporter_analysis_day_file_found: **True**
- reporter_analysis_found: **True**
- reporter_analysis_path: `tmp\report_check\dev\analysis\reporter_analysis\reporter_analysis_2026-03-18.json`

## Next Command
- `python scripts/run_agent_pipeline_trace_report.py --run-id ec2c700d34564245903c51ccf6d606d8 --json`
- `python scripts/query_trade_reason_chain.py --run-id ec2c700d34564245903c51ccf6d606d8 --only-broker-success`