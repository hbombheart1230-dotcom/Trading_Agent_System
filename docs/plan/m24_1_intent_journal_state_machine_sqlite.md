# M24-1: Intent Journal State Machine (SQLite Scaffold)

- Date: 2026-02-17
- Goal: start M24 by adding a strict intent state machine and SQLite-first state/journal storage scaffold.

## Scope (minimal)

1. Define strict intent lifecycle states and transition rules:
   - `pending_approval -> approved -> executing -> executed|failed`
   - `pending_approval -> rejected`
2. Add SQLite store for:
   - latest intent state (`intent_state`)
   - append-only transition journal (`intent_journal`)
3. Keep milestone additive only (no integration change to existing approval/execution path yet).

## Implemented

- File: `libs/supervisor/intent_state_store.py`
  - Added state constants and transition policy.
  - Added `IntentStateMachine`:
    - `can_transition(...)`
    - `apply(...)`
  - Added `SQLiteIntentStateStore`:
    - `ensure_intent(...)`
    - `get_state(...)`
    - `transition(...)`
    - `list_journal(...)`
  - DB schema:
    - `intent_state(intent_id, state, updated_ts, version)`
    - `intent_journal(id, intent_id, ts, from_state, to_state, reason, meta_json, execution_json)`

- File: `tests/test_m24_1_intent_state_store.py`
  - Added tests for:
    - valid state-machine transitions
    - invalid transition rejection
    - terminal idempotent retry semantics
    - SQLite state/journal persistence and ordering
    - pending->rejected path

## Safety Notes

- Additive scaffold only; existing `IntentStore(JSONL)` and `ApprovalService` runtime path are unchanged in M24-1.
- Integration into live approval/execution flow is deferred to next M24 steps.
