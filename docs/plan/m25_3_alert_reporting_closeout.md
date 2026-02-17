# M25-3: Alert Reporting and Closeout

- Date: 2026-02-17
- Goal: connect alert policy evaluation to daily operator artifacts and a single M25 closeout gate.

## Scope (minimal)

1. Add one M25 closeout script that runs:
   - metrics schema freeze validation (M25-1)
   - alert policy threshold gate (M25-2)
   - daily report generation
2. Emit alert artifacts (`json` + `md`) for handover/audit.
3. Add pass/fail regression tests for default and injected-critical scenarios.

## Implemented

- File: `scripts/run_m25_closeout_check.py`
  - Seeds deterministic closeout events for selected day.
  - Runs:
    - `check_metrics_schema_v1`
    - `check_alert_policy_v1`
    - `generate_daily_report`
  - Writes:
    - `alert_policy_<day>.json`
    - `alert_policy_<day>.md`
  - Options:
    - `--inject-critical-case`
    - `--fail-on critical|warning|none`
  - Return codes:
    - `0`: pass
    - `3`: fail

- File: `tests/test_m25_3_alert_reporting_closeout.py`
  - Added pass-case closeout test.
  - Added fail-case closeout test with critical alert injection.

## Safety Notes

- Reporting/ops gate only.
- Runtime execution logic unchanged.
