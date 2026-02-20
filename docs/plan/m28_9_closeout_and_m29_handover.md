# M28-9: Closeout and M29 Handover

- Date: 2026-02-21
- Goal: finalize M28 with one reproducible deployment/runtime platformization closeout gate and hand over to M29 governance/audit phase.

## Scope (minimal)

1. Add one closeout script that validates end-to-end M28 stack:
   - M28-1 runtime profile scaffold
   - M28-2 lifecycle hooks
   - M28-3 rollout checklist + rollback readiness
   - M28-4 startup preflight gate
   - M28-5 scheduler/worker preflight wrapper
   - M28-6 launch hook integration
   - M28-7 deploy-target launch templates
   - M28-8 deployment registration helpers
2. Add pass/fail tests for closeout behavior.
3. Provide handover notes for M29 governance/audit/recovery milestones.

## Implemented

- File: `scripts/run_m28_closeout_check.py`
  - Runs M28-1..M28-8 check scripts in JSON mode.
  - Uses isolated closeout artifacts under:
    - `--work-dir` (default `data/state/m28_closeout`)
    - `--report-dir` (default `reports/m28_closeout`)
  - Creates deterministic dev env file for preflight/wrapper checks.
  - Validates additional evidence:
    - M28-1 `profiles.prod.ok == true`
    - M28-2 `startup_2.reason == active_run`
    - M28-3 `go_no_go == go` and `rollback_ready == true`
    - M28-4 runtime smoke boot success
    - M28-5/6 scheduler+worker role readiness
    - M28-7/8 `required_fail_total == 0`
  - Supports failure injection with `--inject-fail` (M28-8 fail path).
  - Exit code:
    - `0`: pass
    - `3`: fail

- File: `tests/test_m28_9_closeout_check.py`
  - Added pass-case closeout test.
  - Added fail-case test using `--inject-fail`.
  - Added script entrypoint import-resolution regression test.

## Handover Notes (to M29)

- M28 now has a full deployment/runtime platform baseline:
  - profile-gated startup/shutdown lifecycle controls
  - rollout/go-no-go + rollback procedure artifacts
  - scheduler/worker launch wrappers with preflight enforcement
  - deploy-target templates and registration helper scaffolds
- M29 can start from this baseline for:
  - audit linkage completeness checks
  - log archive integrity/retention checks
  - incident timeline reconstruction
  - disaster recovery restore/replay validation

## Safety Notes

- This milestone is closeout/reporting integration only and does not add direct live-execution authority.
