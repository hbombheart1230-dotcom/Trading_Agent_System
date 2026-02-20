# M27-7: Portfolio Guard Notify Context

- Date: 2026-02-20
- Goal: make portfolio-guard alert signals first-class in scheduled ops notifications.

## Scope (minimal)

1. Include portfolio-guard alert code summary in closeout/notification payloads.
2. Ensure notification dedup key reflects portfolio-guard alert-code changes.
3. Add a focused check script and regression tests for this behavior.

## Implemented

- File: `scripts/run_m25_closeout_check.py`
  - Extended closeout `alert_policy` summary with:
    - `alert_codes`
    - `portfolio_guard_alert_total`
    - `portfolio_guard_alert_codes`

- File: `libs/reporting/alert_notifier.py`
  - `build_batch_notification_payload` now carries:
    - `alert_policy.alert_codes`
    - `alert_policy.portfolio_guard_alert_total`
    - `alert_policy.portfolio_guard_alert_codes`
  - `build_slack_webhook_payload` now includes `pg_alerts=<count>` and top `pg_codes`.
  - `_dedup_key_from_payload` now includes alert-code context, so different portfolio-guard alert sets are not treated as identical notifications.

- File: `scripts/run_m27_portfolio_guard_notify_check.py`
  - Verifies portfolio-guard alert extraction in notify payload.
  - Verifies dedup key changes when alert-code composition changes.
  - Exit code:
    - `0`: pass
    - `3`: fail

- File: `tests/test_m27_7_portfolio_guard_notify_context.py`
  - Added payload extraction, dedup-key delta, check-script pass/fail, and script entrypoint import-resolution regressions.

## Operator Usage

```bash
python scripts/run_m27_portfolio_guard_notify_check.py --json
python scripts/run_m27_portfolio_guard_notify_check.py --inject-fail --json
```

## Notes for M27-8

- Next step can add policy-driven notification routing/escalation by portfolio-guard alert class (for example, warning vs critical channel split).
