# M25-8: Slack Webhook Provider

- Date: 2026-02-17
- Goal: extend M25 notification delivery with a Slack incoming-webhook provider while preserving existing webhook/noise-control behavior.

## Scope (minimal)

1. Add `slack_webhook` provider option in notifier and batch CLI.
2. Keep dedup/rate-limit suppression policy shared with webhook provider.
3. Add regression tests and runbook/docs sync.

## Implemented

- File: `libs/reporting/alert_notifier.py`
  - Added `build_slack_webhook_payload(...)`.
  - Extended provider routing: `none | webhook | slack_webhook`.
  - Reused M25-7 suppression state (`dedup_suppressed`, `rate_limited`) for both webhook providers.
  - Generalized webhook sender result provider label via `provider_name`.

- File: `scripts/run_m25_ops_batch.py`
  - Extended `--notify-provider` choices with `slack_webhook`.

- File: `tests/test_m25_6_alert_notification_adapter.py`
  - Added Slack provider success test (payload shape + provider field).

- File: `tests/test_m25_5_ops_batch_hook.py`
  - Updated forwarding test to verify `slack_webhook` provider is passed through batch hook.

## Safety Notes

- Existing `webhook` behavior is unchanged.
- Slack path is opt-in via `M25_NOTIFY_PROVIDER=slack_webhook`.
- Alert gating return codes are unchanged; channel send failure handling still follows `M25_NOTIFY_FAIL_ON_ERROR`.
