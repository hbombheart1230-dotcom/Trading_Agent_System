# M28-2: Runtime Lifecycle Hooks

- Date: 2026-02-20
- Goal: add safe startup/shutdown hooks for scheduler/worker runtime lifecycle control.

## Scope (minimal)

1. Add runtime lifecycle state file hooks (`startup` / `shutdown`) with active-run blocking.
2. Add operator check script for lifecycle hook pass/fail behavior.
3. Add tests and docs for lifecycle preflight usage.

## Implemented

- File: `libs/runtime/runtime_lifecycle.py`
  - Added lifecycle hooks:
    - `startup_hook(state_path, lock_stale_sec, now_epoch)`
    - `shutdown_hook(state_path, run_id, final_status, now_epoch)`
  - Behavior:
    - blocks duplicate startup when active run lock is fresh
    - allows takeover for stale running locks
    - validates run-id on shutdown when provided

- File: `scripts/run_m28_runtime_lifecycle_hooks_check.py`
  - Runs deterministic sequence:
    - startup success
    - duplicate startup blocked (`active_run`)
    - shutdown
    - startup success after shutdown
  - Supports failure injection (`--inject-fail`) via shutdown run-id mismatch.
  - Exit code:
    - `0`: pass
    - `3`: fail

- File: `tests/test_m28_2_runtime_lifecycle_hooks.py`
  - Added lifecycle hook and check-script regressions.
  - Added script entrypoint import-resolution regression.

## Operator Usage

```bash
python scripts/run_m28_runtime_lifecycle_hooks_check.py --json
python scripts/run_m28_runtime_lifecycle_hooks_check.py --inject-fail --json
```

## Notes for M28-3

- Next step should wire lifecycle state + runtime profile checks into a single startup preflight command for deploy profiles.
