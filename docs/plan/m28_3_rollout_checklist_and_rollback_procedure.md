# M28-3: Rollout Checklist and Rollback Procedure

- Date: 2026-02-21
- Goal: provide one deterministic rollout preflight check and rollback procedure artifact for deployment/runtime platformization.

## Scope (minimal)

1. Reuse M28-1 and M28-2 checks as rollout prerequisites.
2. Generate explicit go/hold decision from required checklist items.
3. Emit rollback-ready status and ordered rollback procedure steps.

## Implemented

- File: `scripts/run_m28_rollout_rollback_check.py`
  - Runs:
    - `run_m28_runtime_profile_scaffold_check.py`
    - `run_m28_runtime_lifecycle_hooks_check.py`
  - Builds required rollout checklist with evidence strings.
  - Produces:
    - `go_no_go` (`go` / `hold`)
    - `rollback_ready`
    - `rollback_procedure` (ordered steps)
  - Writes artifacts:
    - `m28_rollout_check_<day>.json`
    - `m28_rollout_check_<day>.md`
  - Supports `--inject-fail` for red-path validation.

- File: `tests/test_m28_3_rollout_rollback_check.py`
  - pass case
  - injected fail case
  - script entrypoint import-resolution case

## Operator Usage

```bash
python scripts/run_m28_rollout_rollback_check.py --json
python scripts/run_m28_rollout_rollback_check.py --inject-fail --json
```

## Notes for M28 closeout

- M28 rollout/go-live readiness now has explicit:
  - profile gate evidence
  - lifecycle gate evidence
  - rollback procedure artifact
