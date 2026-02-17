# M24-7: Intent State Ops Visibility

- Date: 2026-02-17
- Goal: provide operator-facing visibility for SQLite intent state/journal health with stuck-execution detection.

## Scope (minimal)

1. Add one ops query CLI for:
   - current intent state summary
   - journal transition totals
   - recent journal rows
   - stuck `executing` detection and gate
2. Add regression tests for JSON summary, filter behavior, stuck gate, and missing DB path handling.

## Implemented

- File: `scripts/query_intent_state_store.py`
  - Added SQLite intent-state query CLI:
    - path resolution: `--state-db-path` -> `INTENT_STATE_DB_PATH` -> `--intent-log-path` + `.db`
    - filters: `--state`, `--limit`
    - stuck detection: `--stuck-executing-sec`, `--require-no-stuck`
    - JSON mode: `--json`
  - Summary fields:
    - `current_state_total`
    - `journal_transition_total` (`from_state->to_state`)
    - `stuck_executing_total`, `stuck_executing`
    - `latest_states`
  - Return codes:
    - `0`: query success
    - `2`: missing/invalid DB query path
    - `3`: stuck executing detected when `--require-no-stuck` enabled

- File: `tests/test_m24_7_intent_state_ops_query.py`
  - Added JSON summary regression test.
  - Added state-filter regression test.
  - Added stuck-executing gate regression test (`rc=3`).
  - Added missing DB path regression test (`rc=2`).

## Safety Notes

- This milestone is observability-only.
- Approval and execution behavior are unchanged.
