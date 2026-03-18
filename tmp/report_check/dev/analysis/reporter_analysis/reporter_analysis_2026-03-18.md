# Reporter Analysis (2026-03-18)

## Daily Operator Report

- system_health: **RED**
- 2026-03-18: health=RED
- trade_count=6 symbols=3
- monitor_status=overtrading_risk scanner_status=appropriate supervisor_blocked_rate=94.71%
- incident_total=1
- recommended_actions: `["Reduce monitor flip risk by increasing confirmation strictness or widening non-emergency exit thresholds.", "High supervisor block rate: recalibrate strategy aggressiveness and guard limits for better intent quality.", "Run incident postmortem and convert top anomaly into explicit preopen/checklist gate before next session."]`

- market_context: `{"global_sentiment_avg": null, "symbol_sentiment_avg": null, "llm_provider_top": {"openrouter": 25, "openai": 1}, "llm_model_top": {"openrouter/free": 25, "minimax/minimax-m2.5": 1}}`
- trades_executed: **12**
- trades_blocked: **215**
- major_decisions: `["defensive", "RegimeMomentumV1", "OpenAIStrategist"]`
- anomalies: `["unexpected_rapid_exit"]`

## Trade Decision Summaries

- trade_summary_total: **6**
| symbol | buy_reason | sell_reason | holding_duration_sec | exit_trigger |
| --- | --- | --- | ---: | --- |
| 322000 | unspecified | unspecified | 0 | hard_stop |
| 000660 | unspecified | unspecified | 1867 | peak_drawdown |
| 000660 | unspecified | unspecified | 832 | peak_drawdown |
| 000660 | unspecified | unspecified | 1549 | take_profit |
| 000660 | unspecified | unspecified | 2231 | take_profit |
| 005930 | unspecified | unspecified | 1484 | peak_drawdown |

## Trade Summary

- trade_count: **6**
- symbols_traded: `["000660", "005930", "322000"]`

## Decision Chains

- run_total: **338**
- rendered_run_total: **200**
- run_id=230a5fb2dad642d9aad96782b78f3c99 symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-
- run_id=1f93c89fdb27485db2253ad15bd247e6 symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-
- run_id=cc9978bb2a85437db7a6db43c9819fb6 symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-
- run_id=99ad100120384a2089d5cae6f704c2c5 symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-
- run_id=2c7aac846cd645d7862af3913e6bd2f8 symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-
- run_id=57b7350b58e64e7597fd0aa19435d620 symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-
- run_id=d9fd04f2eff34bc4bda66c808a451c07 symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-
- run_id=07fd410398ba47b1a33f3c5669460901 symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-
- run_id=a755e8ee166d4cc2afaccc7502fd1682 symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-
- run_id=87f336fa794543d88cb38d4c91903b0f symbol=- action=- supervisor=UNKNOWN execution=UNKNOWN buy_reason=- sell_reason=-

## Decision Trace Chain Summary

- run_total: **288**
- complete_chain_total: **20**
- run_id=230a5fb2dad642d9aad96782b78f3c99 selected=- monitor=confirmed_exit_signal supervisor=- executor=- complete=False
- run_id=1f93c89fdb27485db2253ad15bd247e6 selected=- monitor=pending_exit_lock supervisor=- executor=- complete=False
- run_id=cc9978bb2a85437db7a6db43c9819fb6 selected=- monitor=pending_exit_lock supervisor=- executor=- complete=False
- run_id=99ad100120384a2089d5cae6f704c2c5 selected=- monitor=pending_exit_lock supervisor=- executor=- complete=False
- run_id=2c7aac846cd645d7862af3913e6bd2f8 selected=- monitor=pending_exit_lock supervisor=- executor=- complete=False
- run_id=57b7350b58e64e7597fd0aa19435d620 selected=- monitor=pending_exit_lock supervisor=- executor=- complete=False
- run_id=d9fd04f2eff34bc4bda66c808a451c07 selected=- monitor=pending_exit_lock supervisor=- executor=- complete=False
- run_id=07fd410398ba47b1a33f3c5669460901 selected=- monitor=confirmed_exit_signal supervisor=- executor=- complete=False
- run_id=a755e8ee166d4cc2afaccc7502fd1682 selected=- monitor=pending_exit_lock supervisor=- executor=- complete=False
- run_id=87f336fa794543d88cb38d4c91903b0f selected=- monitor=pending_exit_lock supervisor=- executor=- complete=False

## Strategist Evaluation

- themes_proposed: `["broad_market_leaders"]`
- actual_market_leaders_by_scanner: `["032820", "000660", "005930", "047040"]`
- theme_alignment_status: **aligned**
- assessment: Strategist themes were reflected in scanner filtering.

## Scanner Evaluation

- scanner_summary_total: **69**
- selected_symbol_top: `{"032820": 33, "000660": 24, "005930": 10, "047040": 2}`
- no_candidate_total: **0**
- avg_top_score: **1.2536**
- selection_status: **appropriate**
- assessment: Scanner selected symbols consistently with sufficient candidate pool.

## Monitor Evaluation

- monitor_summary_total: **288**
- monitor_reason_top: `{"hold": 186, "no_position": 69, "pending_exit_lock": 18, "confirmed_exit_signal": 9, "exit_signal_pending_confirmation": 4, "min_hold_active": 2}`
- rapid_buy_sell_cycles: **1**
- monitor_status: **overtrading_risk**
- assessment: Monitor shows overtrading risk; tighten exit confirmation or thresholds.

## Supervisor Activity

- verdict_total: **454**
- approved_total: **24**
- blocked_total: **430**
- blocked_rate: **94.71%**
- blocked_reason_top: `{"noop_intent_skipped": 430}`
- assessment: Supervisor blocks are elevated; review guard thresholds.

## Intent Flow Analysis

- intents_created: **0**
- intents_blocked: **215**
- intents_approved: **12**
- intents_executed: **12**
- reason_top: `{"noop_intent_skipped": 215, "monitor:hold": 186, "monitor:no_position": 69, "monitor:pending_exit_lock": 18, "monitor:confirmed_exit_signal": 9, "monitor:exit_signal_pending_confirmation": 4, "min_hold_blocked": 2, "monitor:min_hold_active": 2}`

## Strategy Effectiveness

- Strategist favored broad_market_leaders theme.
- Scanner selected 032820 most frequently.
- Monitor exited mostly due to hold.
- Reporter focus priority: exit_quality

## Overtrading Diagnostics

- rapid_buy_sell_cycles(<120s): **1**
- noise_exit_related_count: **4**
- frequent_guard_block_count: **0**
- guard_block_rate: **0.00%**

## Incident / Post-Mortem Support

- incident_total: **1**
- [YELLOW] unexpected_rapid_exit: rapid_buy_sell_cycles=1

## Improvement Suggestions

- report_focus_targets: `["exit_quality", "scanner_fit", "guard_blocks"]`
- Reduce monitor flip risk by increasing confirmation strictness or widening non-emergency exit thresholds.
- High supervisor block rate: recalibrate strategy aggressiveness and guard limits for better intent quality.
- Run incident postmortem and convert top anomaly into explicit preopen/checklist gate before next session.

## AI Review (Passive Optional Layer)

- ai_review_status: **parse_error**
- ai_review_model: `minimax/minimax-m2.5`
- ai_review_reason: ai_response_missing_required_keys:ai_summary, ai_findings, ai_root_causes, ai_improvement_suggestions, ai_run_grade, ai_agent_evaluations, ai_evidence_links:{"ai_summary": "Run 2026-03-18 shows mixed performance. Strategist and scanner performed well with aligned themes and appropriate symbol selection. However, mon...
- ai_review_fallback_enriched: true
- ai_run_grade: **N/A**
- ai_summary: Monitor behavior showed overtrading or rapid exit pressure in this run window.
- ai_findings: `["Monitor behavior showed overtrading or rapid exit pressure in this run window."]`
- ai_root_causes: `["Exit handling and monitor confirmation logic remained the dominant source of instability."]`
- ai_improvement_suggestions: `["Reduce monitor flip risk by increasing confirmation strictness or widening non-emergency exit thresholds."]`
- ai_agent_evaluations: `{"strategist": "good", "scanner": "good", "monitor": "needs_improvement", "supervisor": "needs_improvement", "executor": "good"}`
- ai_findings_detailed:
  - text: Monitor behavior showed overtrading or rapid exit pressure in this run window.
    evidence_keys: `["monitor_exit_quality", "overtrading_risk"]`
- ai_root_causes_detailed:
  - text: Exit handling and monitor confirmation logic remained the dominant source of instability.
    evidence_keys: `["monitor_exit_quality", "overtrading_risk"]`
- ai_improvement_suggestions_detailed:
  - text: Reduce monitor flip risk by increasing confirmation strictness or widening non-emergency exit thresholds.
    evidence_keys: `["monitor_exit_quality"]`

## Developer Summary

- decision_chain_run_total=338
- blocked_total=430 approved_total=24
- monitor_confirmed_exit_total=9
- scanner_no_candidate_total=0
- blocked_reason_top: `{"noop_intent_skipped": 430}`
- monitor_reason_top: `{"hold": 186, "no_position": 69, "pending_exit_lock": 18, "confirmed_exit_signal": 9, "exit_signal_pending_confirmation": 4, "min_hold_active": 2}`

## Source Artifacts

- trade_explain_json: `tmp\report_check\trade_explain\trade_explain_2026-03-18.json`
- trade_explain_md: `tmp\report_check\trade_explain\trade_explain_2026-03-18.md`
- operator_summary_json: `tmp\report_check\operator_summary\operator_summary_2026-03-18.json`
- operator_summary_md: `tmp\report_check\operator_summary\operator_summary_2026-03-18.md`
- decision_story_md: `tmp\report_check\decision_story\decision_story_2026-03-18.md`
- run_cards_md: `tmp\report_check\run_cards\run_cards_2026-03-18.md`
- decision_story_total: `227`
- run_card_total: `227`
