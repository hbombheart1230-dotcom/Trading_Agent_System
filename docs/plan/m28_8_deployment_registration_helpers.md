# M28-8: Deployment Registration Helpers

- Date: 2026-02-21
- Goal: add deploy-target registration helper templates (Windows Task Scheduler and Linux systemd install flows) bound to M28 launch templates.

## Scope (minimal)

1. Generate role-based registration helper scripts for scheduler/worker.
2. Validate helper scripts reference expected deploy commands and template artifacts.
3. Keep deterministic red-path checks with injected worker helper mismatch.

## Implemented

- File: `scripts/generate_m28_registration_helpers.py`
  - Generates helper scripts:
    - `windows/register_scheduler_task.ps1`
    - `windows/register_worker_task.ps1`
    - `linux/install_scheduler_service.sh`
    - `linux/install_worker_service.sh`
  - Windows helpers include:
    - `schtasks /Create ... /XML ... /F`
  - Linux helpers include:
    - `systemctl daemon-reload/enable/restart`
  - Supports `--inject-fail` for worker helper mismatch path.

- File: `scripts/run_m28_registration_helper_check.py`
  - Runs helper generator and validates expected command/template references.
  - Produces artifacts:
    - `m28_registration_helpers_<day>.json`
    - `m28_registration_helpers_<day>.md`
  - Supports fail-path validation via `--inject-fail`.

- File: `tests/test_m28_8_registration_helpers.py`
  - pass case
  - injected fail case
  - script entrypoint import-resolution case

## Operator Usage

```bash
python scripts/run_m28_registration_helper_check.py --profile dev --template-dir deploy/m28_launch_templates --json
python scripts/run_m28_registration_helper_check.py --profile dev --template-dir deploy/m28_launch_templates --inject-fail --json
```

## Notes for M28-9

- Next step should add one M28 closeout gate that aggregates M28-1..M28-8 outputs into a single deployment-readiness decision.
