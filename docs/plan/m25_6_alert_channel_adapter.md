# M25-6: Alert Channel Adapter

- Date: 2026-02-17
- Goal: connect M25 batch outcomes to a real notification channel (webhook first) with policy-based delivery control.

## Scope (minimal)

1. Add reusable alert notifier module.
2. Integrate notifier into M25 ops batch hook.
3. Support safe rollout:
   - `notify_on` policy
   - `dry_run` mode
   - optional fail-on-notify-error behavior

## Implemented

- File: `libs/reporting/alert_notifier.py`
  - Added payload builder for M25 batch summaries.
  - Added webhook sender (`POST application/json`).
  - Added channel policy gate:
    - `provider=none|webhook`
    - `notify_on=always|failure|success`
    - `dry_run`

- File: `scripts/run_m25_ops_batch.py`
  - Added notify options:
    - `--notify-provider`
    - `--notify-on`
    - `--notify-webhook-url`
    - `--notify-timeout-sec`
    - `--notify-dry-run`
    - `--fail-on-notify-error`
  - Notification result is persisted in batch status JSON under `notify`.
  - Added optional `rc=5` when notify fails and `--fail-on-notify-error` is enabled.

- File: `tests/test_m25_6_alert_notification_adapter.py`
  - Added notifier unit tests for:
    - provider none skip
    - webhook dry-run
    - webhook success

- File: `tests/test_m25_5_ops_batch_hook.py`
  - Added batch integration test for `fail_on_notify_error` -> `rc=5`.

## Safety Notes

- Notification path is additive and opt-in (`provider=none` default).
- Existing closeout/alert gate behavior is unchanged unless notify options are enabled.
