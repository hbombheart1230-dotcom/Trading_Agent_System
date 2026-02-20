# M27-10: Closeout and M28 Handover

- Date: 2026-02-20
- Goal: finalize M27 with one reproducible closeout gate and hand over to M28 platformization.

## Scope (minimal)

1. Add one closeout script that validates end-to-end M27 stack:
   - M27-1 allocation policy
   - M27-2 conflict resolution
   - M27-3 portfolio budget boundary guard
   - M27-4 runtime portfolio guard integration
   - M27-5 metrics reporting
   - M27-6 alert policy
   - M27-7 notify context
   - M27-8 notify routing escalation
   - M27-9 notify ops query
2. Add pass/fail tests for closeout behavior.
3. Sync roadmap/index/project-tree docs for M27 closeout status.

## Implemented

- File: `scripts/run_m27_closeout_check.py`
  - Runs M27-1..M27-9 check scripts in JSON mode.
  - Uses isolated closeout artifacts under:
    - `--event-log-dir` (default `data/logs/m27_closeout`)
    - `--report-dir` (default `reports/m27_closeout`)
  - Validates additional evidence:
    - M27-5 `portfolio_guard.applied_total >= 1`
    - M27-6 `alert_policy_rc == 0`
    - M27-8 selected provider is `slack_webhook`
    - M27-9 `escalated_total >= 1`
  - Supports failure injection with `--inject-fail` (M27-9 fail path).
  - Exit code:
    - `0`: pass
    - `3`: fail

- File: `tests/test_m27_10_closeout_check.py`
  - Added pass-case closeout test.
  - Added fail-case test using `--inject-fail`.
  - Added script entrypoint import-resolution regression test.

## Handover Notes (to M28)

- M27 now has portfolio-level policy and ops observability baseline:
  - multi-strategy allocation and intent conflict handling
  - runtime guard application and metrics/alert integration
  - portfolio-guard-aware notification routing and escalation query path
- M28 can start from this baseline for:
  - deployment profile standardization (dev/staging/prod)
  - scheduler/worker startup-shutdown lifecycle hardening
  - config/secret profile validation and rollback playbooks

## Safety Notes

- This milestone is closeout/reporting integration only and does not add direct live-execution authority.
