# M28-5: Scheduler/Worker Launch Wrapper

- Date: 2026-02-21
- Goal: wire startup preflight into scheduler/worker launch flow so operators run one wrapper command instead of manual preflight per role.

## Scope (minimal)

1. Run `m28-4` startup preflight automatically for both scheduler and worker roles.
2. Aggregate role-level launch readiness into one checklist artifact.
3. Preserve deterministic fail-path validation with injection mode.

## Implemented

- File: `scripts/run_m28_scheduler_worker_launch_wrapper_check.py`
  - Calls `run_m28_startup_preflight_check.py` for:
    - `scheduler`
    - `worker`
  - Per-role preflight includes:
    - strict runtime profile gate
    - lifecycle startup/shutdown hooks
    - commander runtime once smoke boot
  - Produces aggregated checklist and artifacts:
    - `m28_scheduler_worker_launch_<day>.json`
    - `m28_scheduler_worker_launch_<day>.md`
  - Supports `--inject-fail`:
    - injects worker active-run lock failure path.

- File: `tests/test_m28_5_scheduler_worker_launch_wrapper_check.py`
  - pass case
  - injected fail case
  - script entrypoint import-resolution case

## Operator Usage

```bash
python scripts/run_m28_scheduler_worker_launch_wrapper_check.py --profile dev --env-path .env --json
python scripts/run_m28_scheduler_worker_launch_wrapper_check.py --profile dev --env-path .env --inject-fail --json
```

## Notes for M28-6

- Next step should connect this wrapper to actual process launch hooks (task scheduler/service manager) for fully automatic startup policy enforcement.
