# M24-2: Approval Flow Integration with SQLite Intent State

- Date: 2026-02-17
- Goal: connect M24-1 SQLite intent state/journal scaffold to the existing approval execution flow.

## Scope (minimal)

1. Wire `ApprovalService` to mirror state transitions into SQLite intent store.
2. Keep existing JSONL intent journal behavior for backward compatibility.
3. Add failure-path handling so execution exceptions are recorded as `failed`.

## Implemented

- File: `libs/approval/service.py`
  - Added optional `state_store` integration:
    - auto-derives DB path from env `INTENT_STATE_DB_PATH` or JSONL intent path suffix (`.db`)
  - Added safe helpers:
    - `_safe_state_ensure(...)`
    - `_safe_state_transition(...)`
  - Approval path now mirrors state transitions:
    - `pending_approval -> approved`
    - `approved -> executing`
    - `executing -> executed`
    - `executing -> failed` (on execution exception)
  - Reject path mirrors:
    - `pending_approval -> rejected`
  - Added strict-state guards:
    - reject blocked after approved/executing/executed
    - approve blocked on failed/executing/rejected states

- File: `tests/test_m24_2_approval_state_store_integration.py`
  - Added tests for:
    - approve->execute transition sequence in SQLite journal
    - reject path transition
    - execution exception -> failed transition
    - reject-after-approved strict-state block

## Safety Notes

- Existing JSONL journal remains active (compatibility preserved).
- SQLite state mirror is additive and enables stricter idempotent execution hardening for upcoming M24 steps.
