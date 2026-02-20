# M28-6: Launch Hook Integration

- Date: 2026-02-21
- Goal: enforce startup preflight in actual launcher flow via a reusable wrapper for scheduler/worker process hooks.

## Scope (minimal)

1. Add one generic launcher that blocks process start when preflight fails.
2. Validate scheduler/worker launch integration path using wrapped command execution.
3. Keep deterministic red-path coverage with injected preflight failure.

## Implemented

- File: `scripts/launch_with_preflight.py`
  - Generic launcher wrapper:
    - runs `run_m28_startup_preflight_check.py`
    - blocks launch when preflight is red
    - executes wrapped command only after green preflight
  - Supports:
    - `--role {scheduler,worker}`
    - `--profile {dev,staging,prod}`
    - `--env-path`
    - `--state-path`
    - `--report-dir`
    - `--inject-fail`
    - `--json`
    - wrapped command via `-- <command ...>`

- File: `scripts/run_m28_launch_hook_integration_check.py`
  - Integration check for scheduler/worker launch hooks.
  - Invokes `launch_with_preflight.py` for both roles with deterministic wrapped command.
  - Produces artifacts:
    - `m28_launch_hook_integration_<day>.json`
    - `m28_launch_hook_integration_<day>.md`
  - Supports `--inject-fail` (worker side preflight fail path).

- File: `tests/test_m28_6_launch_hook_integration_check.py`
  - pass case
  - injected fail case
  - script entrypoint import-resolution case

## Operator Usage

```bash
python scripts/launch_with_preflight.py --role scheduler --profile dev --env-path .env -- python -c "print('scheduler start')"
python scripts/run_m28_launch_hook_integration_check.py --profile dev --env-path .env --json
python scripts/run_m28_launch_hook_integration_check.py --profile dev --env-path .env --inject-fail --json
```

## Notes for M28-7

- Next step should add deploy-target launch templates (Task Scheduler/systemd) that call this wrapper as first step for startup policy enforcement.
