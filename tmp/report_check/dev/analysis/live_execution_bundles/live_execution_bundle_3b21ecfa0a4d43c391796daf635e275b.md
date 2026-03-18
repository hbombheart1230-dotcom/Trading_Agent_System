# Aggregated Execution Bundle (3b21ecfa0a4d43c391796daf635e275b)

- day: **2026-03-18**
- story_anchor: **BUY 000660 x1 | run 3b21ecfa0a4d43c391796daf635e275b**
- story_type: **simulation**
- execution_mode: **simulation (mock broker)**

## Market Context

Market regime was neutral with a defensive playbook. Global sentiment scored -0.01 and VIX was 22.37. No explicit macro stress flags were active in the strategist frame. 35 headlines were considered across 7 market or symbol targets.

- Market regime: neutral
- Market sentiment: neutral
- Playbook: defensive
- Global sentiment score: -0.01
- VIX / fear index level: 22.37
- Dollar index move: 0.21%
- Themes detected: broad_market_leaders
- Defensive mode: not enabled

## Why This Symbol

Scanner selected 000660 as rank #1 out of 5 candidates because it led on trading value, theme and sector alignment, sentiment support.

- Universe scanned: 5
- Selected rank: #1
- Ranking basis: trading value, theme and sector alignment, sentiment support
- Selected because: highest combined scanner score (1.272)
- Selection sources: top_value, sector_theme
- Chart / feature coverage: 10/12
- Why not others: 005930 was weaker because top_value+sector_theme; 032820 was weaker because top_value+top_volume+sector_theme

## Filters / Gates

Scanner and guard checks passed 5 of 8 visible gates. Chart completeness was pass with 10/12 captured features.

- liquidity filter: PASS - top value or trading-value input supported the selection
- turnover filter: FAIL - top volume or turnover input supported the selection
- sector/theme alignment: PASS - theme boost or sector source matched the strategist frame
- chart completeness filter: PASS - 10/12 captured chart features
- sentiment gate: PASS - news/global sentiment contribution was 0.255
- risk gate: PASS - risk score was 0.462 and supervisor allow=True
- price anomaly filter: NOT_AVAILABLE - price anomaly check was not captured in this run
- spread/slippage filter: NOT_AVAILABLE - spread or slippage diagnostics were not captured in this run

## Monitor / Trigger Reasoning

BUY was triggered because no_position.

- Posture: BUY
- Trigger type: no_position
- Monitor reason: no_position
- Position age: 0 seconds
- Stop loss: 6.01%
- Effective stop: not_captured%
- Effective stop reason: not_captured
- Take profit: 0.59%

## Guard / Approval

Supervisor approved the order because Allowed.

- Supervisor verdict: approve
- Supervisor allow: yes
- Guard reason: Allowed
- Action reviewed: BUY
- Symbol reviewed: 000660
- Approval mode: not captured in the execution trace

## Execution Outcome

BUY order for 000660 x1 was approved and recorded successfully in simulation mode.

- Execution outcome: recorded
- Quantity: 1
- Execution mode: simulation (mock broker)
- Broker environment: mock
- Order status: 모의투자 매수주문완료
- Order number: 0043780

## Reporter Status

Monitor behavior showed overtrading or rapid exit pressure in this run window.

- Reporter status: linked
- Reporter reason: A same-day reporter analysis was linked to this run.
- Reporter grade: N/A
- Reporter summary: Monitor behavior showed overtrading or rapid exit pressure in this run window.

## Operator Conclusion

Current action is BUY. BUY order for 000660 x1 was approved and recorded successfully in simulation mode.


## Timeline

- strategist_frame: Market regime was neutral with a defensive playbook. Global sentiment scored -0.01 and VIX was 22.37. No explicit macro stress flags were active in the strategist frame. 35 headlines were considered across 7 market or symbol targets.
- scanner_ranking: Scanner selected 000660 as rank #1 out of 5 candidates because it led on trading value, theme and sector alignment, sentiment support.
- monitor_signal: BUY was triggered because no_position.
- supervisor_approval: Supervisor approved the order because Allowed.
- broker_result: BUY order for 000660 x1 was approved and recorded successfully in simulation mode.
- reporter_output: Monitor behavior showed overtrading or rapid exit pressure in this run window.

## Artifacts

- agent_pipeline_trace_json: `tmp\report_check\dev\analysis\live_execution_bundles\agent_pipeline_trace\agent_pipeline_trace_3b21ecfa0a4d43c39179.json`
- agent_pipeline_trace_md: `tmp\report_check\dev\analysis\live_execution_bundles\agent_pipeline_trace\agent_pipeline_trace_3b21ecfa0a4d43c39179.md`
- trade_explain_json: `tmp\report_check\dev\analysis\trade_explain\trade_explain_2026-03-18.json`
- trade_explain_md: `tmp\report_check\dev\analysis\trade_explain\trade_explain_2026-03-18.md`
- reporter_analysis_json: `tmp\report_check\dev\analysis\reporter_analysis\reporter_analysis_2026-03-18.json`
- reporter_analysis_md: `tmp\report_check\dev\analysis\reporter_analysis\reporter_analysis_2026-03-18.md`
- operator_summary_json: `tmp\report_check\operator_summary\operator_summary_2026-03-18.json`
- operator_summary_md: `tmp\report_check\operator_summary\operator_summary_2026-03-18.md`
- canonical_commander_json: ``
- canonical_strategist_json: ``
- canonical_scanner_json: ``
- canonical_monitor_json: ``
- canonical_supervisor_json: ``
- canonical_executor_json: ``
- trade_lifecycle_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_01\lifecycle\trade_lifecycle.json`
- trade_story_input_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_01\ai_trade_report\ai_trade_report_input.json`
- ai_trade_report_input_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_01\ai_trade_report\ai_trade_report_input.json`
- trade_report_json: ``
- trade_report_md: ``
- ai_trade_report_json: ``
- ai_trade_report_md: ``
- strategist_llm_response_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_01\strategist\strategist_llm_response.json`
- ai_trade_report_llm_response_json: ``
- strategist_evidence_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_01\evidence\strategist_evidence.json`
- scanner_evidence_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_01\evidence\scanner_evidence.json`
- monitor_timeline_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_01\evidence\monitor_timeline.json`
