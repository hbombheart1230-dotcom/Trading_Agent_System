# Agent Pipeline Trace (91be9a2735a247aaacc669da0c8004b8)

- day: **2026-03-18**
- event_log_path: `data\logs\events.jsonl`
- evidence_log_path: `data\evidence_ledger\events.jsonl`

## Commander
- mode: **integrated_chain**
- agents: `["commander_router", "strategist", "scanner", "monitor", "decision", "supervisor", "executor", "reporter"]`
- route_ts: `2026-03-18T03:13:29+00:00`
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
- selected_symbol: **000660**
- entry_reason=take_profit exit_reason=take_profit monitor_reason=confirmed_exit_signal
- position_age_seconds=2229 min_hold_blocked=False sell_cooldown_blocked=False
- thresholds: `{"hard_stop_pct": 0.01, "stop_loss_pct": 0.08, "take_profit_pct": 0.006855840000000001, "max_hold_sec": 0, "time_stop_sec": 0, "trailing_stop_pct": 0.04, "vol_expansion_ratio": 1.6, "news_shock_threshold": 0.0, "peak_drawdown_exit_pct": 0.00368, "vwap_breakdown_pct": 0.005, "intraday_low_break_pct": 0.002, "trend_strength_floor": -0.15, "eod_flat_cutoff_min": 10, "effective_stop_loss_pct": 0.01, "effective_stop_reason": "hard_stop"}` min_hold=360 sell_cooldown=300 confirm_ticks=1
- strategy_frame_adjustments: `["monitor_guidance:defensive_exit"]`

## Supervisor
- verdict=approve allow=True reason=Allowed

## Executor
- execution_attempted=True ok=True broker_code=0
- execution_mode=real kiwoom_mode=mock broker_env=mock effective_mode=mock_broker_http
- api_id=ORDER_SUBMIT url=https://mockapi.kiwoom.com/api/dostk/ordr action=SELL symbol=000660 qty=1

## Reporter
- in_run_trace_available: **False**
- reporter_analysis_day_file_found: **True**
- reporter_analysis_found: **True**
- reporter_analysis_path: `tmp\report_check\dev\analysis\reporter_analysis\reporter_analysis_2026-03-18.json`

## Next Command
- `python scripts/run_agent_pipeline_trace_report.py --run-id 91be9a2735a247aaacc669da0c8004b8 --json`
- `python scripts/query_trade_reason_chain.py --run-id 91be9a2735a247aaacc669da0c8004b8 --only-broker-success`