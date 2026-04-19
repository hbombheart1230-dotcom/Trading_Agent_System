# M13 Live Boundary Audit

## Goal

Make the live runtime entry surface coherent:

- `scripts/run_session.py` stays the official entrypoint
- `scripts/run_m13_live_loop.py` becomes a thin boundary wrapper
- reusable runtime ownership moves into libs/graphs modules

This is an operational cleanup. It must not change trading semantics.

## Current Call Chain

### Official operator-facing path

`python scripts/run_session.py --mode live --phase intraday`

### Actual intraday route

1. `scripts/run_session.py`
2. `build_execution_plan(...)`
3. `_dispatch(plan)`
4. import `scripts.run_m13_live_loop.main`
5. call `main(argv)` in-process
6. `scripts/run_m13_live_loop.py`
7. loop over `graphs.pipelines.m13_live_loop.run_m13_once(...)`

This means the current live runtime is primarily a direct Python entry flow.
It is not a shell-script-owned runtime.

## What Is Good Already

### `scripts/run_session.py`

Good boundary responsibilities already present:

- CLI parsing
- phase/mode routing
- official entrypoint visibility
- compatibility with live/mock/preopen/intraday/closeout/watch

### `scripts/run_m13_live_loop.py`

Good boundary responsibilities already present:

- CLI/env bridge for live intraday
- top-level loop start/stop
- single-instance process guard

## What Is Still Too Thick

### `scripts/run_m13_live_loop.py`

This script still owns logic that should not stay script-local long term:

- `_resolve_env_path(...)`
- `_first_universe_symbol(...)`
- `_to_int(...)`
- `_to_bool(...)`
- `_resolve_path_from_root(...)`
- `_session_hard_gate_enabled(...)`
- `_acquire_lock(...)`
- `_refresh_lock(...)`
- `_release_lock(...)`
- initial state bootstrap via `_build_initial_state(...)`
- market-open hard gate decision
- loop ownership details around lock refresh timing

This is still script-bound runtime logic, not just process boundary glue.

## Hidden Dependency Risk

`scripts/run_offhours_validation_loop.py` currently imports helper functions from
`scripts/run_m13_live_loop.py`.

Imported helpers observed today:

- `_acquire_lock`
- `_first_universe_symbol`
- `_release_lock`
- `_resolve_path_from_root`
- `_to_bool`
- `_to_int`

This means `run_m13_live_loop.py` is already acting like an accidental helper
module. That is exactly the boundary smell we should remove.

## Recommended Extraction Shape

### Keep in `scripts/run_session.py`

- operator-facing CLI
- mode/phase routing
- execution plan generation
- dispatch to runtime backends

### Keep in `scripts/run_m13_live_loop.py`

- thin CLI wrapper
- call into extracted runtime loop owner
- final process exit code mapping

### Move out of `scripts/run_m13_live_loop.py`

Recommended target module family:

- `libs/runtime/session_loop.py`
- or `libs/runtime/session_process.py`

Move:

- lock acquisition / refresh / release
- env/path resolution helpers shared by runtime scripts
- session hard-gate logic
- initial intraday state bootstrap
- main live loop ownership helper

### Leave in graphs/pipelines

- `graphs.pipelines.m13_live_loop.run_m13_once(...)`
- node orchestration semantics
- commander-aware integrated-chain behavior

## Recommended Rollout

### Step 1

Extract shared helpers from `scripts/run_m13_live_loop.py` into a lib module.

Update:

- `scripts/run_m13_live_loop.py`
- `scripts/run_offhours_validation_loop.py`

This is the lowest-risk cleanup because it removes cross-script imports first.

### Step 2

Create one module-owned live loop function, for example:

- `libs.runtime.session_loop.run_live_intraday_loop(...)`

Make `scripts/run_m13_live_loop.py` call that function only.

### Step 3

Re-evaluate whether `scripts/run_session.py` should directly own the intraday
loop without delegating to `scripts/run_m13_live_loop.py`.

Do not do this until Step 1 and Step 2 are stable.

## Non-Goals

- no strategy changes
- no scanner logic changes
- no monitor logic changes
- no report contract changes
- no order semantics changes

## Success Criteria

This cleanup is complete when:

1. `scripts/run_session.py` remains the only official operator-facing entrypoint
2. `scripts/run_m13_live_loop.py` is a thin wrapper
3. no other script imports helper functions from `scripts/run_m13_live_loop.py`
4. lock/session/env helpers live in libs, not scripts
5. live intraday behavior is unchanged
