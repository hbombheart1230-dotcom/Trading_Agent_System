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

## 4. Triage Rules

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
