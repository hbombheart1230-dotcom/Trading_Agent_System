# 2026-05-12 Full-Close Trade Report Gate

## Reason

- `003060` generated a final AI trade report after a 1-share partial SELL while the original BUY quantity was 1000 shares.
- The lifecycle builder treated any SELL attached to an entry as a closed trade, so the reporter wrote final artifacts before full liquidation.
- A later 999-share SELL was split into a recovered second trade, which made the report folder misleading.

## Patch

- `libs/reporting/trade_lifecycle_builder.py`
  - Added cumulative exit quantity tracking.
  - A SELL closes a lifecycle only when cumulative exit quantity is at least the entry quantity.
  - Partial SELLs stay in the same open lifecycle as `partial_exit` timeline events with remaining quantity.
- `libs/reporting/trade_report_runtime_policy.py`
  - Added `partial_exit_awaiting_full_close` pending reason.
- `libs/reporting/trade_report_runtime_generation.py`
  - Pending lifecycle plans now use `pending_no_report` and do not reuse stale existing reports.
- `libs/reporting/live_execution_bundle_runner.py`
  - Pending/open/partial lifecycle states remove stale final report artifacts and skip `ai_trade_report` / `ai_trade_summary` writes.
- `libs/reporting/trade_report_ai.py`
  - Deterministic closed-trade summaries now prefer the lifecycle close summary over stale operator HOLD text.

## Current 003060 Cleanup

- Regenerated `reports/trades/2026-05-12/1000/TRD_20260512_003060_01` as one closed lifecycle:
  - entry run: `8ef0083d5c244a80981650bb252cb258`
  - partial exit run: `75bb5c2f16654f5681c4986973741e51`
  - final exit run: `4ce5ae64ba8a483ea1f864c6172830db`
- Moved stale split folder:
  - from `reports/trades/2026-05-12/1000/TRD_20260512_003060_02`
  - to `reports/dev/stale_trade_reports/2026-05-12/1000/TRD_20260512_003060_02`

## Validation

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_lifecycle_builder.py libs\reporting\trade_report_runtime_policy.py libs\reporting\trade_report_runtime_generation.py libs\reporting\live_execution_bundle_runner.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py::test_build_deterministic_trade_report_closed_lifecycle_prefers_lifecycle_summary tests\test_trade_lifecycle_builder.py tests\test_intraday_trade_reports.py::test_intraday_trade_reports_policy_helpers_gate_open_trade_generation tests\test_live_execution_bundle_report.py::test_live_execution_bundle_report_keeps_open_lifecycle_without_exit tests\test_live_execution_bundle_report.py::test_live_execution_bundle_report_defers_partial_exit_report_until_full_close -q`
- Result: `8 passed`.

## Live Rule

- Final trade reports are generated only after full close.
- Partial exits are recorded for lifecycle traceability, but do not create final AI report or AI summary artifacts.

## Restart

- Live session restarted after the patch.
- Active lock heartbeat after restart:
  - pid: `11780`
  - heartbeat: `2026-05-12T02:18:54+00:00`
