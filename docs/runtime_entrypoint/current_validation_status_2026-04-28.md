# Current Validation Status 2026-04-28

Snapshot time: 2026-04-28 12:38 KST

Runtime command:

```powershell
venv\Scripts\python.exe scripts\run_session.py --mode live --phase intraday --tick-pipeline integrated_chain --sleep-sec 30 --allow-offhours
```

Current process state:

- parent process: `3804`
- live loop lock owner: `20176`
- lock file: `data/state/m13_live_loop.lock`
- latest observed heartbeat: `2026-04-28T12:37:43+09:00`
- latest canonical run inspected: `reports/canonical/2026-04-28/a7a5849c88f74a8bb0f18a05a9d83e99`

## Verification Matrix

| Area | Current verification | Evidence | Remaining live check |
| --- | --- | --- | --- |
| `docs/runtime_entrypoint` | Verified. Official entrypoint is running and the lock heartbeat is refreshing. | `scripts/run_session.py`, `libs/runtime/live_loop_runner.py`, `libs/runtime/live_loop_lock.py`, `data/state/m13_live_loop.lock` | Continue watching that only one lock owner is active after restarts. |
| `docs/commander_control` | Partially live-verified. Commander selects `monitor_only` because an open `000660` position exists. Commander-owned scanner fields include `scanner.policy.market_representative_guard`. | latest `commander.json`, `graphs/commander_runtime.py` | Next flat/full scanner cycle must confirm the representative guard appears in `scanner.json` and changes ranking only under weak-confirmation near-tie conditions. |
| `docs/runtime_memory` | Live-verified for monitor-side memory application. Latest monitor artifact shows `monitor_memory_bias_applied=true`, `monitor_memory_bias_exit_applied=true`, `monitor_memory_bias_hold_applied=false`. | latest `monitor.json`, `libs/runtime/monitor_memory_bias*.py`, `libs/runtime/commander_memory_application_trace.py` | Fresh strategist artifact must still verify `memory_usage_trace` and same-day reporter feedback consumption after the next strategist call. |
| `docs/strategy_horizon_feedback` | Live-verified as observability-only. Latest monitor artifact records `horizon_owner=commander`, `strategy_horizon=intraday`, `observability_only=true`, and actual hold seconds. | latest `monitor.json`, `libs/runtime/strategy_horizon_feedback.py`, `graphs/nodes/monitor_node.py` | Need a real exit event to validate `exit_alignment` and post-exit shadow tracking. |
| `docs/strategist_output` | Code/test verified, but not live-verified in the latest run because current route is `SKIP_MONITOR_ONLY`; no fresh `strategist.json` is produced while holding. | `graphs/nodes/strategist_node.py`, `libs/contracts/agent_outputs.py`, strategist tests | Next strategist call must show `selected_themes`, `theme_strength_packet`, `news_collection_policy`, strategist explanation, and memory usage fields together. |
| `docs/kiwoom_truth` | Code/test verified for theme reader and day-trade truth paths. Current monitor-only run confirms live position monitoring continues, but no new fill truth was produced in the latest run. | `libs/read/kiwoom_theme_reader.py`, `libs/reporting/kiwoom_day_trade_truth.py`, `graphs/nodes/build_portfolio_snapshot.py` | Next buy/sell must validate first-write live truth, `ka10077` repeated-symbol tie-breaker, and report truth provenance. |
| `docs/trade_report_plan` | Code/test verified. Existing 2026-04-28 closed trades have `ai_trade_report` artifacts. Current live run has no new closed trade after restart. | `reports/trades/2026-04-28/*/reports`, `scripts/run_ai_trade_report_batch.py`, `scripts/run_live_execution_bundle_report.py` | Next closed trade must confirm live first-write still uses report LLM while manual regeneration defaults to no-LLM. |

## Tests Run

All tests below passed in the current workspace:

- `tests/test_run_ai_trade_report_batch.py tests/test_trade_bundle_assembly.py tests/test_trade_report_ai.py`: 121 passed
- `tests/test_kiwoom_theme_reader.py tests/test_kiwoom_day_trade_truth.py tests/test_m31_17_theme_candidate_flow_upgrade.py`: 17 passed
- `tests/test_strategist_explanation_contract.py tests/test_strategist_reasoning_quality.py tests/test_strategy_horizon_feedback.py tests/test_strategist_frame_llm_integration.py`: 52 passed
- `tests/test_commander_memory_policy.py tests/test_scanner_memory_bias.py tests/test_monitor_memory_bias.py tests/test_m21_commander_runtime_entry.py tests/test_scanner_policy_overlay.py tests/test_scanner_monitor_compatibility.py`: 104 passed

## Code-Matching Map

Trade report:

- Runtime/manual regeneration: `scripts/run_ai_trade_report_batch.py`
- Live first-write bundle/report: `scripts/run_live_execution_bundle_report.py`
- Report assembly: `libs/reporting/trade_report_ai.py`, `libs/reporting/trade_bundle_assembly.py`

Kiwoom truth:

- Portfolio hot path: `graphs/nodes/build_portfolio_snapshot.py`, `libs/read/kiwoom_portfolio_reader.py`
- Theme packet: `libs/read/kiwoom_theme_reader.py`
- Day-trade truth/report truth: `libs/reporting/kiwoom_day_trade_truth.py`

Strategist output:

- Strategy frame, theme/news/memory/horizon fields: `graphs/nodes/strategist_node.py`
- Canonical artifact contract: `libs/contracts/agent_outputs.py`

Strategy horizon feedback:

- Commander horizon policy and exit-vs-intent model: `libs/runtime/strategy_horizon_feedback.py`
- Monitor recording surface: `graphs/nodes/monitor_node.py`, `libs/contracts/agent_outputs.py`

Runtime memory:

- Packet loading and arbitration: `libs/runtime/memory_packet_loader.py`, `graphs/commander_runtime.py`
- Scanner/monitor deterministic bias: `libs/runtime/scanner_memory_bias*.py`, `libs/runtime/monitor_memory_bias*.py`
- Application trace: `libs/runtime/commander_memory_application_trace.py`

Commander control:

- Runtime routing and scanner policy ownership: `graphs/commander_runtime.py`
- Representative-stock scanner guard: `graphs/nodes/scanner_node.py`

Runtime entrypoint:

- Operator entrypoint: `scripts/run_session.py`
- Live loop backend: `scripts/run_m13_live_loop.py`
- Lock and loop ownership: `libs/runtime/live_loop_lock.py`, `libs/runtime/live_loop_runner.py`

## Additional Development Checklist

1. Add a lightweight live validation reporter that reads the latest canonical run and emits this matrix automatically.
2. Surface `market_representative_guard` under commander summary `scanner_fields`, not only in `policy_sources.commander_owned_scanner_fields`.
3. Add an optional scanner shadow-probe path for monitor-only periods so scanner policy changes can be validated while a position is open without creating orders.
4. Validate the next fresh strategist call against `docs/strategist_output`: selected themes, news collection policy, memory usage trace, and reporter feedback packet must all appear in one artifact.
5. Validate the next closed trade against `docs/trade_report_plan` and `docs/kiwoom_truth`: broker truth provenance, live first-write LLM report, and deterministic regeneration mode must remain distinct.
6. Validate the first post-exit shadow sample after a real sell before allowing horizon feedback to change hold behavior.
