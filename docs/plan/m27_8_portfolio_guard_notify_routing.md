# M27-8: Portfolio Guard Notify Routing

- Date: 2026-02-20
- Goal: route high-risk portfolio-guard alert days to a dedicated notification channel.

## Scope (minimal)

1. Add portfolio-guard-aware provider escalation in notification adapter.
2. Expose escalation config in ops batch CLI/env profile.
3. Add routing check script and regressions.

## Implemented

- File: `libs/reporting/alert_notifier.py`
  - Added route resolution policy:
    - if `portfolio_guard_alert_total >= escalation_min`, switch to `portfolio_guard_provider`
    - optional dedicated webhook URL override
  - Added notify output fields:
    - `selected_provider`
    - `route_reason`
    - `portfolio_guard_alert_total`
    - `escalated`

- File: `scripts/run_m25_ops_batch.py`
  - Added options/env plumbing:
    - `--notify-portfolio-guard-escalation-min`
    - `--notify-portfolio-guard-provider`
    - `--notify-portfolio-guard-webhook-url`
  - Ops notify event now records route metadata (`route_reason`, `escalated`, selected `provider`).

- File: `scripts/run_m27_portfolio_guard_notify_routing_check.py`
  - Verifies provider escalation on portfolio-guard alert conditions.
  - `--inject-fail` validates gate failure path.

- Files:
  - `tests/test_m27_8_portfolio_guard_notify_routing.py`
  - `tests/test_m25_5_ops_batch_hook.py`
  - `tests/test_m25_6_alert_notification_adapter.py`
  - Added routing and forwarding regressions.

## Operator Usage

```bash
python scripts/run_m27_portfolio_guard_notify_routing_check.py --json
python scripts/run_m27_portfolio_guard_notify_routing_check.py --inject-fail --json
```

## Suggested Env Profile

```env
M25_NOTIFY_PORTFOLIO_GUARD_ESCALATION_MIN=1
M25_NOTIFY_PORTFOLIO_GUARD_PROVIDER=slack_webhook
M25_NOTIFY_PORTFOLIO_GUARD_WEBHOOK_URL=
```
