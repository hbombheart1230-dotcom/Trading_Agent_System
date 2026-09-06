# Step5C: durable execution owner

Cleanup prerequisite: c77f830 (2998 passed, 1 skipped).

## Boundary and identity

The canonical packet path and legacy execute_order path retain all existing
guards and Supervisor decisions. Only after approval does the execution-owner
adapter claim approved -> executing in SQLite, before any executor call. This
placement records real approval rather than pretending that an unapproved
packet has been approved. CAS never substitutes for policy approval.

Explicit intent_id is preserved. Conflicting explicit IDs fail closed. Missing
IDs are deterministic hashes of execution scope, run_id, symbol, action and
original broker reference. Scope includes execution/broker mode and a digest of
account identity. Two distinct same-symbol/same-action intents in one run must
provide distinct explicit intent_id values. A changed payload under one ID is
an identity conflict, not permission to submit again.

Automatically generated cancellations use a deterministic child intent_id from
scope, original broker reference and cancel/modify terms, independent of polling
tick. No execution_intent_id/decision_id/execution_id is introduced. Earlier
Monitor artifacts may legitimately predate ID assignment; packet/order,
Supervisor input, execution artifact and store share the assigned ID thereafter.
No historical artifact is rewritten.

## Storage and lifecycle

SQLiteIntentStateStore remains the single state owner. Its existing database is
used, defaulting to repository-root/data/state/intent_state.db; the optional
INTENT_STATE_DB_PATH must be identical for every participating process and on a
local durable filesystem. Tests receive a per-test isolated path, inherited by
subprocesses. An additive binding table records payload digest and private owner
capability in that same database, not a second execution state store.

BEGIN IMMEDIATE, expected-state UPDATE and journal/binding writes commit in one
transaction. New, already policy-approved submissions record pending/approved
and atomically claim executing. Existing pending rows are NOT auto-approved.
Existing executing/executed/failed/rejected rows never obtain another owner.

ACCEPTED -> executed means broker acceptance, NOT fill completion.
REJECTED / NOT_SENT after claiming -> failed (no implicit replay).
UNKNOWN / crash / normalization exception -> executing, reconciliation needed.
Terminal persistence failure preserves the broker outcome and executing lock.
CAS/backend failure -> NOT_SENT, physical broker calls zero.

Existing Step5B classification, mutation retry=0, UNKNOWN quarantine and
cancel-confirmation rules remain unchanged. Read queries do not acquire ownership.
Direct raw Executor calls without an OrderIntent remain Step5B transport APIs;
they are not an alternate approved OrderIntent execution entry point. New logical
order paths must use this adapter. Cross-tick newly-created intents are still
subject to existing symbol/TTL/risk guards; this layer does not infer that two
different IDs are the same trading decision.

## Validation and limitations

Focused coverage includes successful ownership, sequential and OS-process
duplicates, restart, terminal/failed/UNKNOWN no replay, backend failure, independent
IDs, same-symbol different IDs, CANCEL/MODIFY, identity conflicts and real
HttpClient+RealExecutor timeout composition with a fake network/token provider.
Automatic reconciliation and operator unlock controls are not implemented here.
No live restart, broker connection, historical data rewrite or policy tuning is
part of this change. Step5D requires its own scope approval; readiness does not
authorize an automatic live rollout.

## Recorded verification (2026-09-06)

- Cleanup full regression: 2998 passed, 1 skipped, exit 0 (c77f830).
- Step5C focused regression before final artifact assertions: 145 passed, exit 0.
- Final Step5C tree full regression, including artifact identity assertions and
  process-crash/persistence-failure regressions: 3012 passed, 1 skipped,
  exit 0, 206.82 seconds.
- Real spawned-process contention permits one executor call; a restarted process
  with the same identity performs zero additional calls. Crash leaves executing.
- Unavailable CAS database performs zero executor calls. RealExecutor/HttpClient
  fake-transport timeout performs one physical submission and no duplicate retry.
- No live restart or push was performed. These are isolated tests, not a claim
  of successful live broker reconciliation or multi-host deployment validation.
