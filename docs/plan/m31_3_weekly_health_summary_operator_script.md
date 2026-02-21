# M31-3: Weekly Post-GoLive Health Summary Operator Script

- Date: 2026-02-21
- Goal: provide one operator entrypoint that summarizes weekly health from event logs and post-go-live alert/policy artifacts.

## Scope (minimal)

1. Aggregate one-week event-log health signal (`total/error/error_rate/run_total`).
2. Aggregate weekly post-go-live policy levels (`normal/watch/incident`) and manual-approval consistency.
3. Aggregate weekly final signoff presence and decision counts.

## Implemented

- File: `scripts/run_m31_weekly_health_summary.py`
  - Inputs:
    - `--event-log-path`
    - `--policy-report-dir` (`m30_post_golive_policy_<day>.json`)
    - `--signoff-report-dir` (`m30_final_golive_signoff_<day>.json`)
    - `--week-end`, `--days`
    - thresholds: `--max-error-rate`, `--max-incident-days`
  - Outputs:
    - `m31_weekly_health_<start>_to_<end>.json`
    - `m31_weekly_health_<start>_to_<end>.md`
  - Includes required checklist:
    - policy artifact presence
    - weekly error-rate guard
    - incident-day guard
    - incident/manual-approval consistency guard
  - Supports `--inject-fail` for operator red-path drill.

- File: `tests/test_m31_3_weekly_health_summary.py`
  - pass case
  - injected fail case
  - script entrypoint import-resolution case

## Operator Usage

```bash
python scripts/run_m31_weekly_health_summary.py \
  --event-log-path data/logs/events.jsonl \
  --policy-report-dir reports/m30_post_golive \
  --signoff-report-dir reports/m30_golive \
  --report-dir reports/m31_weekly_health \
  --week-end 2026-02-21 \
  --days 7 \
  --json
```

## Why This Matters

- Gives operators one weekly health artifact for M31 stabilization review.
- Keeps M31 based on M30 artifacts (no duplication of policy/signoff logic).
- Enables consistent weekly review loop and escalation tuning decisions.
