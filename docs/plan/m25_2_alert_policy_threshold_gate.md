# M25-2: Alert Policy Threshold Gate

- Date: 2026-02-17
- Goal: convert frozen metrics schema v1 into actionable alert threshold checks for operator triage.

## Scope (minimal)

1. Add one alert policy gate CLI that evaluates critical/warning thresholds from daily metrics.
2. Cover required policy targets:
   - strategist failure pressure
   - circuit-open pressure
   - guard block spike
   - approved-vs-executed anomaly
   - broker API 429 pressure
3. Add regression tests for pass/critical-fail/warning-fail modes.

## Implemented

- File: `scripts/check_alert_policy_v1.py`
  - Reads metrics via:
    - `--metrics-json-path` (direct), or
    - `generate_metrics_report` from `--event-log-path`/`--report-dir`/`--day`.
  - Thresholds:
    - `--llm-success-rate-min`
    - `--llm-circuit-open-rate-max`
    - `--execution-blocked-rate-max`
    - `--execution-approved-executed-gap-max`
    - `--api-429-rate-max`
  - Policy output:
    - `alerts[]` with `severity`, `code`, `value`, `threshold`
    - `severity_total`, `values`, `thresholds`
  - Fail mode:
    - `--fail-on critical|warning|none` (default: `critical`)
  - Return codes:
    - `0`: policy pass
    - `3`: policy fail by fail mode
    - `2`: metrics load error

- File: `tests/test_m25_2_alert_policy_threshold_gate.py`
  - pass-case test under default thresholds
  - critical fail-case test (default `fail_on=critical`)
  - warning fail-case test (`--fail-on warning`)

## Safety Notes

- Observability and operator policy only.
- Runtime execution/approval behavior is unchanged.
