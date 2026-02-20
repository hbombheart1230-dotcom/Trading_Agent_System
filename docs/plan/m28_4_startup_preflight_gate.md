# M28-4: Startup Preflight Gate

- Date: 2026-02-21
- Goal: bind runtime profile validation and lifecycle startup/shutdown hooks into one deterministic startup gate before runtime boot.

## Scope (minimal)

1. Run strict runtime profile validation before startup lock acquisition.
2. Verify lifecycle startup lock and commander-runtime smoke boot in one command.
3. Verify lifecycle shutdown lock release and emit preflight artifacts.

## Implemented

- File: `scripts/run_m28_startup_preflight_check.py`
  - Runs strict profile check via `check_runtime_profile.py`.
  - Runs lifecycle hooks:
    - `startup_hook(...)`
    - `shutdown_hook(...)`
  - Runs canonical runtime smoke boot via `run_commander_runtime_once.py` on green startup/profile path.
  - Emits required checklist + pass/fail evidence.
  - Writes artifacts:
    - `m28_startup_preflight_<day>.json`
    - `m28_startup_preflight_<day>.md`
  - Supports red-path injection (`--inject-fail`) by seeding an active runtime lock.

- File: `tests/test_m28_4_startup_preflight_check.py`
  - pass case
  - injected fail case (`active_run`)
  - script entrypoint import-resolution case

## Operator Usage

```bash
python scripts/run_m28_startup_preflight_check.py --profile dev --env-path .env --json
python scripts/run_m28_startup_preflight_check.py --profile dev --env-path .env --inject-fail --json
```

## Notes for M28-5

- Next step should cover startup gate integration into scheduler/worker launch wrapper so operators do not need to run preflight manually.
