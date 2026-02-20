# Runtime Lifecycle Runbook (M28-2)

- Last updated: 2026-02-20
- Scope: scheduler/worker startup and shutdown safety hooks.

## 1. Lifecycle State Variables

```env
M28_LIFECYCLE_STATE_PATH=data/state/m28_runtime_lifecycle.json
M28_LIFECYCLE_LOCK_STALE_SEC=1800
```

## 2. Validate Lifecycle Hook Sequence

```powershell
python scripts/run_m28_runtime_lifecycle_hooks_check.py --json
```

Return codes:
- `0`: lifecycle hook sequence pass
- `3`: lifecycle hook sequence fail

## 3. Expected Runtime Behavior

- First startup:
  - acquires runtime state lock (`status=running`)
- Duplicate startup (fresh lock):
  - blocked with reason `active_run`
- Shutdown:
  - transitions state to `stopped`
- Startup after shutdown:
  - allowed

## 4. Failure Triage

- `active_run` on expected first startup:
  - state file likely stale or previous process is active.
  - validate process ownership and lock age.
- `run_id_mismatch` on shutdown:
  - shutdown caller is using wrong runtime run-id.
- repeated startup failure after shutdown:
  - verify state file write permissions and runtime state path.
