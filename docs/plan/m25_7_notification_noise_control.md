# M25-7: Notification Noise Control

- Date: 2026-02-17
- Goal: reduce alert spam by adding deterministic suppression policy for repeated/bursty batch notifications.

## Scope (minimal)

1. Add dedup suppression for same batch-alert signature in a configurable window.
2. Add rate-limit suppression for total notification volume in a configurable window.
3. Keep behavior opt-in and backward-compatible with existing M25-6 webhook adapter.

## Implemented

- File: `libs/reporting/alert_notifier.py`
  - Added state-backed suppression policy in `notify_batch_result(...)`:
    - `state_path`
    - `dedup_window_sec`
    - `rate_limit_window_sec`
    - `max_per_window`
  - Added suppression reasons:
    - `dedup_suppressed`
    - `rate_limited`
  - Added lightweight local state persistence (`version=1`, `events[]`) for notification history.

- File: `scripts/run_m25_ops_batch.py`
  - Added CLI/env wiring:
    - `--notify-state-path` (`M25_NOTIFY_STATE_PATH`)
    - `--notify-dedup-window-sec` (`M25_NOTIFY_DEDUP_WINDOW_SEC`)
    - `--notify-rate-limit-window-sec` (`M25_NOTIFY_RATE_LIMIT_WINDOW_SEC`)
    - `--notify-max-per-window` (`M25_NOTIFY_MAX_PER_WINDOW`)
  - Forwarded these options to notifier call.

- File: `tests/test_m25_6_alert_notification_adapter.py`
  - Added M25-7 unit tests:
    - duplicate webhook notifications suppressed by dedup window
    - burst notifications suppressed by rate-limit window

- File: `tests/test_m25_5_ops_batch_hook.py`
  - Added integration test that verifies new noise-control args are forwarded.

## Safety Notes

- Defaults are conservative and non-breaking.
- Suppression only affects outbound notifications, not closeout/alert gate verdicts.
- Batch JSON keeps explicit suppression reason in `notify.reason` for operator visibility.
