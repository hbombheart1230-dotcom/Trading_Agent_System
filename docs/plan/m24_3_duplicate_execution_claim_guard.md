# M24-3: Duplicate Execution Claim Guard (SQLite CAS)

- Date: 2026-02-17
- Goal: prevent duplicate execution attempts by enforcing an atomic execution claim step on SQLite intent state.

## Scope (minimal)

1. Add compare-and-swap (CAS) transition support in SQLite state store.
2. Make `ApprovalService` use SQLite state as authoritative status for approval/execute decisions.
3. Block second execution attempt when one worker already claimed `executing`.

## Implemented

- File: `libs/supervisor/intent_state_store.py`
  - Extended `transition(...)` with `expected_from_state`.
  - Added atomic update path:
    - update succeeds only when current DB state matches expected state
    - mismatches return deterministic state mismatch error

- File: `libs/approval/service.py`
  - Added `_state_status(...)` and SQLite-first status checks in `preview/approve/reject`.
  - Execution start now uses CAS transition:
    - `approved -> executing` with `expected_from_state=approved`
  - Reject/approve transitions use explicit expected-state constraints.

- File: `tests/test_m24_3_duplicate_execution_claim_guard.py`
  - Added tests for:
    - SQLite status precedence over stale JSONL markers
    - duplicate execution claim blocked across two service instances

## Safety Notes

- Existing JSONL journal remains for backward compatibility and audit.
- CAS guard is additive and focused on duplicate execution prevention.
