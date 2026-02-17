# M25-10: Notification Event Log and Query CLI

- Date: 2026-02-17
- Goal: provide operator-visible delivery observability by logging each batch notification result and exposing a day-level query summary.

## Scope (minimal)

1. Append one notification result event per M25 batch run.
2. Add CLI to summarize notification delivery outcomes by day.
3. Keep closeout/alert gate logic unchanged.

## Implemented

- File: `scripts/run_m25_ops_batch.py`
  - Added `--notify-event-log-path` (`M25_NOTIFY_EVENT_LOG_PATH`).
  - Appends `stage=ops_batch_notify`, `event=result` row after notification attempt.
  - Event payload includes:
    - `provider`, `notify_on`
    - `ok`, `sent`, `skipped`, `reason`, `status_code`
    - `batch_rc`, `closeout_rc`, `day`

- File: `scripts/query_m25_notification_events.py`
  - Added day-filtered summary CLI:
    - `total`, `ok_total`, `fail_total`
    - `sent_total`, `skipped_total`
    - `provider_total`, `reason_total`, `status_code_total`

- File: `tests/test_m25_5_ops_batch_hook.py`
  - Added assertion that batch run creates notification event row.

- File: `tests/test_m25_10_notification_events_query.py`
  - Added summary and empty-log tests for query CLI.

## Safety Notes

- Notification event logging is additive and does not change batch pass/fail semantics.
- Query CLI is read-only against JSONL log and safe for operator use.
