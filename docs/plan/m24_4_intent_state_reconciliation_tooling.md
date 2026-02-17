# M24-4: Intent State Reconciliation Tooling

- Date: 2026-02-17
- Goal: provide reconciliation tooling between JSONL intent journal and SQLite intent state store for recovery drills.

## Scope (minimal)

1. Add one reconciliation CLI that compares:
   - JSONL expected final intent state
   - SQLite current intent state
2. Detect:
   - missing intents in SQLite
   - state mismatches
   - SQLite orphan intents
3. Support optional repair mode by replaying legal state paths from JSONL-derived final state.

## Implemented

- File: `scripts/reconcile_intent_state_store.py`
  - Inputs:
    - `--intent-log-path`
    - `--state-db-path`
    - `--repair`
    - `--json`
  - Compares JSONL/SQLite and reports:
    - missing/mismatch/orphan counts
    - before/after summary
  - Repair mode:
    - resets specific intent rows in SQLite
    - replays legal state path to target final state

- File: `tests/test_m24_4_intent_state_reconcile_script.py`
  - Added tests for:
    - mismatch/missing/orphan detection
    - repair path producing aligned SQLite states

## Safety Notes

- Reconciliation is explicit (`--repair` opt-in).
- Default mode is read-only consistency report.
- Runtime approval/execution path behavior is unchanged.
