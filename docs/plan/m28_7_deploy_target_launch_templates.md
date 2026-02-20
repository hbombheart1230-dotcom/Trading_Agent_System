# M28-7: Deploy-Target Launch Templates

- Date: 2026-02-21
- Goal: provide deploy-ready launch templates (Task Scheduler/systemd) that enforce preflight wrapper at process start.

## Scope (minimal)

1. Generate Windows and Linux launch templates for scheduler/worker roles.
2. Ensure templates reference `launch_with_preflight.py` before runtime command.
3. Add one integration check script and regression tests for pass/fail paths.

## Implemented

- File: `scripts/generate_m28_launch_templates.py`
  - Generates:
    - `windows/scheduler_task.xml`
    - `windows/worker_task.xml`
    - `linux/scheduler.service`
    - `linux/worker.service`
  - Commands include:
    - `scripts/launch_with_preflight.py ... -- python scripts/run_commander_runtime_once.py ...`
  - Supports `--inject-fail` for deterministic worker-template red path.

- File: `scripts/run_m28_deploy_launch_template_check.py`
  - Runs template generator and validates wrapper references for all templates.
  - Produces artifacts:
    - `m28_launch_templates_<day>.json`
    - `m28_launch_templates_<day>.md`
  - Supports `--inject-fail` fail-path validation.

- File: `tests/test_m28_7_deploy_launch_templates.py`
  - pass case
  - injected fail case
  - script entrypoint import-resolution case

## Operator Usage

```bash
python scripts/run_m28_deploy_launch_template_check.py --profile dev --env-path .env --json
python scripts/run_m28_deploy_launch_template_check.py --profile dev --env-path .env --inject-fail --json
```

## Notes for M28-8

- Next step should add deployment registration helpers (e.g., Task Scheduler import command snippets and systemd install commands) with environment-specific profiles.
