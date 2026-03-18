# Aggregated Execution Bundle (78b1ebd804054abc8dc6c25c9a522b12)

- day: **2026-03-18**
- story_anchor: **BUY 000660 x1 | run 78b1ebd804054abc8dc6c25c9a522b12**
- story_type: **simulation**
- execution_mode: **simulation (mock broker)**

## Market Context

Market regime was not_captured with a not_captured playbook. Global sentiment scored 0.00 and VIX was not_captured. No explicit macro stress flags were active in the strategist frame. No strong news input was captured for this run.

- Market regime: not_captured
- Market sentiment: not_captured
- Playbook: not_captured
- Global sentiment score: 0.00
- VIX / fear index level: not_captured
- Dollar index move: not_captured%
- Themes detected: none captured
- Defensive mode: not enabled

## Why This Symbol

Scanner selected 000660 as rank #1 out of 5 candidates because it led on trading value, theme and sector alignment, sentiment support.

- Universe scanned: 5
- Selected rank: #1
- Ranking basis: trading value, theme and sector alignment, sentiment support
- Selected because: highest combined scanner score (1.238)
- Selection sources: top_value, sector_theme
- Chart / feature coverage: 10/12
- Why not others: 005930 was weaker because top_value+sector_theme; 032820 was weaker because top_value+top_volume+sector_theme

## Filters / Gates

Scanner and guard checks passed 5 of 8 visible gates. Chart completeness was pass with 10/12 captured features.

- liquidity filter: PASS - top value or trading-value input supported the selection
- turnover filter: FAIL - top volume or turnover input supported the selection
- sector/theme alignment: PASS - theme boost or sector source matched the strategist frame
- chart completeness filter: PASS - 10/12 captured chart features
- sentiment gate: PASS - news/global sentiment contribution was 0.244
- risk gate: PASS - risk score was 0.472 and supervisor allow=True
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
- Order number: 0082753

## Reporter Status

Monitor behavior showed overtrading or rapid exit pressure in this run window.

- Reporter status: linked
- Reporter reason: A same-day reporter analysis was linked to this run.
- Reporter grade: N/A
- Reporter summary: Monitor behavior showed overtrading or rapid exit pressure in this run window.

## Operator Conclusion

Current action is BUY. BUY order for 000660 x1 was approved and recorded successfully in simulation mode.


## Timeline

- strategist_frame: Market regime was not_captured with a not_captured playbook. Global sentiment scored 0.00 and VIX was not_captured. No explicit macro stress flags were active in the strategist frame. No strong news input was captured for this run.
- scanner_ranking: Scanner selected 000660 as rank #1 out of 5 candidates because it led on trading value, theme and sector alignment, sentiment support.
- monitor_signal: BUY was triggered because no_position.
- supervisor_approval: Supervisor approved the order because Allowed.
- broker_result: BUY order for 000660 x1 was approved and recorded successfully in simulation mode.
- reporter_output: Monitor behavior showed overtrading or rapid exit pressure in this run window.

## Artifacts

- agent_pipeline_trace_json: `tmp\report_check\dev\analysis\live_execution_bundles\agent_pipeline_trace\agent_pipeline_trace_78b1ebd804054abc8dc6.json`
- agent_pipeline_trace_md: `tmp\report_check\dev\analysis\live_execution_bundles\agent_pipeline_trace\agent_pipeline_trace_78b1ebd804054abc8dc6.md`
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
- trade_lifecycle_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_03\lifecycle\trade_lifecycle.json`
- trade_story_input_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_03\ai_trade_report\ai_trade_report_input.json`
- ai_trade_report_input_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_03\ai_trade_report\ai_trade_report_input.json`
- trade_report_json: ``
- trade_report_md: ``
- ai_trade_report_json: ``
- ai_trade_report_md: ``
- strategist_llm_response_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_03\strategist\strategist_llm_response.json`
- ai_trade_report_llm_response_json: ``
- strategist_evidence_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_03\evidence\strategist_evidence.json`
- scanner_evidence_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_03\evidence\scanner_evidence.json`
- monitor_timeline_json: `tmp\report_check\trades\2026-03-18\TRD_20260318_000660_03\evidence\monitor_timeline.json`
