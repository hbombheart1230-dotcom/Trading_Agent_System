# M25-5: Ops Batch Hook

- Date: 2026-02-17
- Goal: provide a scheduler-friendly wrapper that runs M25 closeout with single-instance lock and latest status artifact.

## Scope (minimal)

1. Add one batch wrapper script for periodic execution.
2. Add lock guard to prevent overlapping runs.
3. Persist latest run result to a stable status JSON path.

## Implemented

- File: `scripts/run_m25_ops_batch.py`
  - Wraps `run_m25_closeout_check`.
  - Adds lock lifecycle:
    - `--lock-path`
    - `--lock-stale-sec`
    - returns `rc=4` when lock is active.
  - Writes latest status:
    - `--status-json-path`
    - includes `rc`, `duration_sec`, and nested closeout summary.
  - Supports env defaults:
    - `M25_BATCH_EVENT_LOG_PATH`
    - `M25_BATCH_REPORT_DIR`
    - `M25_BATCH_LOCK_PATH`
    - `M25_BATCH_LOCK_STALE_SEC`
    - `M25_BATCH_STATUS_JSON_PATH`

- File: `tests/test_m25_5_ops_batch_hook.py`
  - pass case: status file written, lock released.
  - fail case: critical injection propagates `rc=3`.
  - lock case: active lock returns `rc=4`.

## Safety Notes

- Operations wrapper only.
- Core runtime decision/execution behavior unchanged.
