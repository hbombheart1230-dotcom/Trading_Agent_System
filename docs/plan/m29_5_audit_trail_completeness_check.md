# M29-5 Audit Trail Completeness Check

- Date: 2026-02-21
- Goal: add an operator-facing audit check that verifies `decision -> execution` linkage integrity from JSONL event logs.

## What Was Added

1. Added `scripts/check_audit_trail_completeness.py`.
   - Inputs:
     - `--event-log-path`
     - `--report-dir`
     - `--day`
     - `--require-actionable`
   - Outputs:
     - JSON + markdown artifacts:
       - `audit_trail_<day>.json`
       - `audit_trail_<day>.md`
   - Core checks per `run_id`:
     - actionable decision (`BUY`/`SELL`) exists
     - execution start exists
     - execution resolution exists (`verdict` / `degrade_policy_block` / `error`)
     - terminal event exists (`end` / `error`)
     - if verdict is `allowed=true`, execution payload event exists
     - orphan execution runs (execution without actionable decision) are detected

2. Added `scripts/run_m29_audit_trail_check.py`.
   - Seeds deterministic pass/fail datasets.
   - Runs the audit checker in JSON mode.
   - Returns closeout-style `ok` + failure reasons.

3. Added `tests/test_m29_6_audit_trail_check.py`.
   - pass case
   - injected fail case
   - file entrypoint import-resolution case (`python scripts/run_m29_audit_trail_check.py ...`)

## Why This Matters

- M29 requires enterprise-grade traceability and recovery readiness.
- This check makes missing or orphaned execution traces visible without manual log inspection.
- The JSON artifact is automation-friendly for closeout and operations batch hooks.
