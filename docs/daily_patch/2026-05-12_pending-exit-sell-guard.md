# 2026-05-12 Pending Exit SELL Guard

## Reason

Today's 000660 exit showed a runtime mismatch:

- broker/executor recorded a SELL for 1 share
- monitor canonical state was still `exit_confirmation_pending:1/2`
- monitor had `exit_triggered=false` and `intent_emitted=false`

This means the trade was profitable, but the execution path was not aligned with the monitor confirmation guard.

## Patch

- Added a decision-layer guard so stale SELL intents are rejected when monitor exit confirmation is still pending.
- Added an executor-layer hard guard so a SELL cannot reach the broker when monitor exit confirmation is blocked or pending.
- Updated trade story reporting so `exit_confirmation_pending` is described as pending/not confirmed, not as a confirmed SELL trigger.

## Validation

- `python -m py_compile graphs\nodes\decision_node.py graphs\nodes\execute_from_packet.py libs\reporting\trade_story_pipeline.py` passed.
- `.\venv\Scripts\python.exe -m pytest tests\test_m17_risk_decision.py::test_m17_exit_intent_rejected_when_monitor_confirmation_pending tests\test_execute_from_packet.py::test_execute_from_packet_blocks_sell_when_monitor_exit_confirmation_pending tests\test_trade_story_pipeline_enrichment.py::test_monitor_reason_human_marks_pending_exit_as_mismatch_not_trigger -q` passed: 3 passed.
- `.\venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py -q` passed: 99 passed.
- `.\venv\Scripts\python.exe -m pytest tests\test_strategy_horizon_feedback.py tests\test_intraday_monitor_signals.py tests\test_scanner_monitor_compatibility.py -q` passed: 81 passed.

## Remaining Note

- The broader `tests\test_execute_from_packet.py` file still has an unrelated existing failure where `252670` is blocked by the asset-universe ETF policy before the mock-broker restricted-symbol guard. This is not part of the pending SELL path.
