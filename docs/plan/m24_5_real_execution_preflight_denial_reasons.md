# M24-5: Real Execution Preflight and Explicit Denial Reasons

- Date: 2026-02-17
- Goal: strengthen real-mode execution preflight checks and provide explicit, stable denial reason codes.

## Scope (minimal)

1. Add preflight guard evaluation API to `RealExecutor`.
2. Standardize denial responses with explicit reason codes.
3. Provide operator CLI for preflight verification before runtime execution.

## Implemented

- File: `libs/execution/executors/real_executor.py`
  - Added `preflight_check(req)`:
    - real mode checks:
      - `EXECUTION_ENABLED=true`
      - `ALLOW_REAL_EXECUTION=true`
      - `KIWOOM_APP_KEY`
      - `KIWOOM_APP_SECRET`
      - `KIWOOM_ACCOUNT_NO`
      - `https` base URL
    - optional allowlist check when symbol exists in request
  - Added explicit denial reason codes (examples):
    - `EXECUTION_DISABLED`
    - `REAL_EXECUTION_NOT_ALLOWED`
    - `MISSING_APP_KEY`
    - `MISSING_APP_SECRET`
    - `MISSING_ACCOUNT_NO`
    - `INVALID_BASE_URL`
    - `ALLOWLIST_BLOCKED`
  - `execute(...)` now uses preflight and raises:
    - `ExecutionDisabledError("[<CODE>] <message>")`

- File: `scripts/check_real_execution_preflight.py`
  - Added operator preflight CLI:
    - optional symbol/allowlist validation
    - JSON/human output
    - exit code `0` (pass), `3` (blocked)

- File: `tests/test_m24_5_real_execution_preflight.py`
  - Added tests for:
    - mock mode pass with execution disabled
    - explicit denial code in real mode when credentials missing
    - denial code included in raised `ExecutionDisabledError`
    - preflight CLI fail-case JSON output

## Safety Notes

- Guarding is stricter and more observable, but still pre-token and pre-HTTP.
- No relaxation of existing real execution safety controls.
