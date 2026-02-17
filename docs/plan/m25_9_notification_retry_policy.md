# M25-9: Notification Retry Policy

- Date: 2026-02-17
- Goal: improve delivery reliability with bounded retry/backoff for transient notification failures.

## Scope (minimal)

1. Add retry/backoff controls for webhook-based providers.
2. Keep retry bounded and operator-configurable via env/CLI.
3. Preserve existing fail-on-notify-error behavior and noise-control policy.

## Implemented

- File: `libs/reporting/alert_notifier.py`
  - Added retry decision for transient HTTP statuses (`429`, `5xx`).
  - Added bounded retry loop in `send_webhook_json(...)` with backoff.
  - Added retry success reason: `sent_after_retry`.
  - Added retry parameters to notifier API:
    - `retry_max`
    - `retry_backoff_sec`

- File: `scripts/run_m25_ops_batch.py`
  - Added CLI/env options:
    - `--notify-retry-max` (`M25_NOTIFY_RETRY_MAX`)
    - `--notify-retry-backoff-sec` (`M25_NOTIFY_RETRY_BACKOFF_SEC`)
  - Forwarded retry options into `notify_batch_result(...)`.

- File: `tests/test_m25_6_alert_notification_adapter.py`
  - Added retry regression test:
    - first attempt `429` -> second attempt success -> `reason=sent_after_retry`.

- File: `tests/test_m25_5_ops_batch_hook.py`
  - Extended forwarding test to verify retry args are passed through batch hook.

## Safety Notes

- Retry is bounded; no infinite loop.
- Non-retryable failures still fail immediately.
- Alert gate verdicts are unchanged; only notification delivery path is hardened.
