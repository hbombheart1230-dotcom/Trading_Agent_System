# M27-9: Portfolio Guard Notify Ops Query

- Date: 2026-02-20
- Goal: expose portfolio-guard escalation visibility in notification event query outputs.

## Scope (minimal)

1. Extend notification event query with escalation-related summary fields.
2. Add filters for escalated/provider/portfolio-guard alert volume.
3. Add dedicated M27-9 check script and regressions.

## Implemented

- File: `scripts/query_m25_notification_events.py`
  - Added filters:
    - `--provider`
    - `--only-escalated`
    - `--min-portfolio-guard-alert-total`
  - Added summary fields:
    - `escalated_total`
    - `portfolio_guard_alert_total_sum`
    - `portfolio_guard_alert_nonzero_total`
    - `portfolio_guard_alert_max`
    - `route_reason_total`

- File: `scripts/run_m27_portfolio_guard_notify_query_check.py`
  - Seeds deterministic `ops_batch_notify` events.
  - Runs query with escalation filters and validates expected summary output.
  - Exit code:
    - `0`: pass
    - `3`: fail

- Files:
  - `tests/test_m25_10_notification_events_query.py`
  - `tests/test_m27_9_portfolio_guard_notify_query.py`
  - Added filter/summary regressions and script entrypoint checks.

## Operator Usage

```bash
python scripts/query_m25_notification_events.py --event-log-path data/logs/m25_notify_events.jsonl --day 2026-02-20 --only-escalated --provider slack_webhook --min-portfolio-guard-alert-total 1 --json
python scripts/run_m27_portfolio_guard_notify_query_check.py --json
```
