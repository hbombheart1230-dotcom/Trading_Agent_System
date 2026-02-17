# Alert Policy Runbook

- Last updated: 2026-02-17
- Scope: M25 alert policy check and closeout operations.

## 1. Configure Threshold Profile

Set values in `.env` (or environment):

```env
ALERT_POLICY_FAIL_ON=critical
ALERT_POLICY_LLM_SUCCESS_RATE_MIN=0.70
ALERT_POLICY_LLM_CIRCUIT_OPEN_RATE_MAX=0.30
ALERT_POLICY_EXECUTION_BLOCKED_RATE_MAX=0.60
ALERT_POLICY_EXECUTION_APPROVED_EXECUTED_GAP_MAX=0
ALERT_POLICY_API_429_RATE_MAX=0.20
```

## 2. Validate Alert Policy

Run against event log for a specific day:

```powershell
python scripts/check_alert_policy_v1.py --event-log-path data/logs/events.jsonl --report-dir reports/m25_alert --day 2026-02-17 --json
```

Return codes:
- `0`: pass under configured `fail_on`
- `3`: alert policy gate failed
- `2`: metrics read/generation failure

## 3. Run M25 Closeout

```powershell
python scripts/run_m25_closeout_check.py --event-log-path data/logs/m25_closeout_events.jsonl --report-dir reports/m25_closeout --day 2026-02-17 --json
```

Artifacts:
- `reports/m25_closeout/metrics_<day>.json`
- `reports/m25_closeout/daily_<day>.json`
- `reports/m25_closeout/alert_policy_<day>.json`
- `reports/m25_closeout/alert_policy_<day>.md`

## 4. Run Scheduled Batch Hook

Batch wrapper (single-instance lock + latest status JSON):

```powershell
python scripts/run_m25_ops_batch.py --event-log-path data/logs/m25_ops_batch_events.jsonl --report-dir reports/m25_ops_batch --status-json-path reports/m25_ops_batch/status_latest.json --json
```

Related env defaults:

```env
M25_BATCH_EVENT_LOG_PATH=data/logs/m25_ops_batch_events.jsonl
M25_BATCH_REPORT_DIR=reports/m25_ops_batch
M25_BATCH_LOCK_PATH=data/state/m25_ops_batch.lock
M25_BATCH_LOCK_STALE_SEC=1800
M25_BATCH_STATUS_JSON_PATH=reports/m25_ops_batch/status_latest.json
M25_NOTIFY_EVENT_LOG_PATH=data/logs/m25_notify_events.jsonl
```

Batch return codes:
- `0`: closeout pass
- `3`: closeout fail (alert/schema gate fail)
- `4`: skipped due to active lock
- `5`: notification send failed with `fail_on_notify_error=true`

Notification channel options:

```env
M25_NOTIFY_PROVIDER=none
M25_NOTIFY_ON=failure
M25_NOTIFY_WEBHOOK_URL=
M25_NOTIFY_TIMEOUT_SEC=5
M25_NOTIFY_STATE_PATH=data/state/m25_notify_state.json
M25_NOTIFY_DEDUP_WINDOW_SEC=600
M25_NOTIFY_RATE_LIMIT_WINDOW_SEC=600
M25_NOTIFY_MAX_PER_WINDOW=3
M25_NOTIFY_RETRY_MAX=1
M25_NOTIFY_RETRY_BACKOFF_SEC=0.5
M25_NOTIFY_DRY_RUN=false
M25_NOTIFY_FAIL_ON_ERROR=false
```

Noise-control policy:
- `M25_NOTIFY_DEDUP_WINDOW_SEC`: suppress same batch-alert signature in window.
- `M25_NOTIFY_RATE_LIMIT_WINDOW_SEC` + `M25_NOTIFY_MAX_PER_WINDOW`: cap total sends in window.
- `M25_NOTIFY_RETRY_MAX` + `M25_NOTIFY_RETRY_BACKOFF_SEC`: retry transient send failures (`429`/`5xx`/network).
- suppress reasons are exposed in batch output as `notify.reason` (`dedup_suppressed` / `rate_limited`).
- provider options: `none`, `webhook`, `slack_webhook` (Slack incoming webhook payload).

Example (webhook):

```powershell
python scripts/run_m25_ops_batch.py --notify-provider webhook --notify-webhook-url https://example.com/hook --notify-on failure --json
```

Example (Slack incoming webhook):

```powershell
python scripts/run_m25_ops_batch.py --notify-provider slack_webhook --notify-webhook-url https://hooks.slack.com/services/... --notify-on failure --json
```

## 5. Query Notification Delivery Summary

```powershell
python scripts/query_m25_notification_events.py --event-log-path data/logs/m25_notify_events.jsonl --day 2026-02-17 --json
```

Key output fields:
- `total`, `ok_total`, `fail_total`
- `sent_total`, `skipped_total`
- `provider_total`, `reason_total`, `status_code_total`

## 6. Triage Rules

- `strategist_success_rate_low` (critical):
  - verify strategist provider/API health and fallback path quality.
- `strategist_circuit_open_rate_high` (critical):
  - inspect repeated provider failures and cooldown behavior.
- `execution_blocked_rate_high` (warning):
  - review guard reasons and allowlist/notional settings.
- `execution_approved_executed_gap_high` (critical):
  - check execution preflight, broker errors, and duplicate-claim handling.
- `broker_api_429_rate_high` (warning):
  - apply backoff/rate control and re-run closeout.
