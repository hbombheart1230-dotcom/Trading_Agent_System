# 2026-09-30 P1.3 CLOSED: Broker Read/Write Gate Fix + Final Paper Acceptance

## Scope

A single, minimal, targeted source fix for the one remaining P1.3 blocker (`PAPER_OPEN_ORDER_QUERY`
failing structurally), plus the minimum required revalidation. No Step5C identity semantics, Step5D
recovery semantics, UEF, strategy, Scanner, Strategist, Q10/Q12, EOD semantics, or ownership semantics
touched. No BUY/SELL order was placed. The real Host runtime was never touched, killed, restarted, or
signaled during this pass -- the fix and its revalidation both used an isolated Docker environment.

## Root cause (traced precisely, not inferred)

Every existing production code path for a read-only Kiwoom broker query --
`KiwoomAccountSnapshotCollector` (account balance, PnL, order history), `KiwoomOrderFillReader`
(open orders), and the generic `CompositeSkillRunner` skill path -- ultimately calls
`RealExecutor.execute()`, whose `preflight_check()` required `EXECUTION_ENABLED=true`
*unconditionally*, for a pure read exactly as for an order mutation. A live P1.3 Paper acceptance run
against the real Kiwoom Paper sandbox (`EXECUTION_MODE=real`, `KIWOOM_MODE=mock`,
`EXECUTION_ENABLED=false`, `ALLOW_REAL_EXECUTION=false`) found `PAPER_AUTH` and `PAPER_ACCOUNT_QUERY`
pass (they happen to use a separate, older, executor-independent read path -- `KiwoomTokenClient`,
`KiwoomPortfolioReader`/`KiwoomAccountClient`) but `PAPER_OPEN_ORDER_QUERY` fail with
`ExecutionDisabledError`, before any network call was even attempted. This incorrectly coupled a
read-only broker-truth operation to the physical order-dispatch safety gate.

## Fix (minimum layer, existing classifier reused)

`libs/execution/executors/real_executor.py::RealExecutor.preflight_check()` now enforces
`EXECUTION_ENABLED` only for requests classified as a mutation by the existing, already-trusted
allowlist-based classifier (`libs/execution/guards/broker_mutation.py::is_mutation_request` --
`kt10000`/`kt10001`/`kt10002`/`kt10003` = BUY/SELL/MODIFY/CANCEL only, plus the unresolved
`"order_submit"` alias). This classifier is not new -- it is the exact same one this file already
trusted for mutation-transport safety (single-attempt dispatch, no replay-on-token-invalid). Any
request it does not positively identify as one of those four order-mutating operations -- including
every account/order-history/open-order read API id -- is no longer blocked by `EXECUTION_ENABLED`. A
request with no specific `req` object at all (an ambiguous, non-read-specific preflight probe) still
fails closed exactly as before, treated as a mutation. The `ALLOW_REAL_EXECUTION` / credential /
base-URL checks for `KIWOOM_MODE=real` are deliberately unchanged and still apply unconditionally to
both reads and writes -- this fix narrows only the `EXECUTION_ENABLED` check, per its own precise scope.

## Tests

`tests/test_p1_3_broker_read_write_gate.py` (new): reads (`kt00018`, `kt00009`, `ka10075`, `kt00007`)
succeed with `EXECUTION_ENABLED=false`; mutations (`kt10000`/`kt10001`/`kt10002`/`kt10003`/
`ORDER_SUBMIT`) remain blocked; explicit BUY and SELL dispatch-blocked proofs; a request-less preflight
probe still fails closed; the live-account `ALLOW_REAL_EXECUTION` guard still applies to reads too;
`EXECUTION_ENABLED=true` is unaffected; a read never reaches the mutation transport path. Two existing
tests (`test_real_executor_mock_mode_allowed.py`, `test_m15_smoke.py`) were updated to use genuine
mutation-shaped requests where they had previously used a generic/unrecognized placeholder that no
longer unambiguously exercised the gate under the new, more precise semantics -- their original safety
intent is fully preserved.

Full regression: identical to the same 11 pre-existing, unrelated failures already confirmed multiple
times this session -- no new failures. Targeted broker/execution/Step5C/Step5D/readiness suites (186+
tests): all passing.

## New P1.3 acceptance revision

Because this is a production source change, per policy a new commit and a new frozen acceptance
revision were created:

- `OLD_FROZEN_SHA`: `68573419f1df90e07f9e7f4497d897d9ffc795fe`
- `NEW_P1_3_ACCEPTANCE_SHA`: `11c7e3c097cc97169643a6249c5e7221cd61b139`

Built from a clean detached worktree at this exact SHA (not the dirty main worktree). Image/source
parity re-verified: 1,072/1,072 baked-in file hashes match the clean worktree exactly; the fixed
`real_executor.py`'s hash was independently confirmed to differ from the old frozen image's copy,
proving the new image genuinely contains the fix.

## Minimum revalidation (per explicit instruction -- the rest of the prior evidence stands, unchanged)

Not rerun (still valid, unaffected by this narrowly-scoped fix): the 6h47m soak, the production-sized
~770 MiB EOD memory rehearsal, the full crash-recovery matrix, the full Step5C/Step5D suites, and the
A/B/C resource benchmark.

Rerun against the new image, using an isolated Docker environment with real Paper credentials:

- Image/source parity: PASS (above).
- Docker startup/health: PASS -- healthy within seconds.
- Ownership acquisition: PASS -- fresh lease, generation 1, no `recovery_required`.
- `EXECUTION_ENABLED=false` verification: confirmed set in the container's own environment.
- `PAPER_AUTH`: PASS -- a real, valid token was confirmed present (obtained during this container's own
  normal tick activity).
- `PAPER_ACCOUNT_QUERY`: PASS -- a real account balance was retrieved.
- `PAPER_OPEN_ORDER_QUERY`: **PASS** -- a real, valid zero-open-orders response was retrieved from the
  Kiwoom Paper sandbox (`VALID_ZERO_RESULT`, not a query failure). This is the fix's direct proof.
- Explicit BUY/SELL dispatch-blocked proof: run live, in the same container, immediately after the
  successful reads above -- both raised `ExecutionDisabledError` (`[EXECUTION_DISABLED]`), confirming
  reads and writes are now correctly and independently gated in the same running environment.
- Open-order readiness fail-closed targeted tests: 43 passed, unaffected by this fix.
- Clean SIGTERM / ownership release: PASS -- stopped in ~2.4s, exit code 0, `OOMKilled=false`, lock file
  removed.

`EXECUTION_DISPATCH_OCCURRED = NO`. `BROKER_ORDER_REQUEST_OCCURRED = NO` throughout. No canonical Host
data was touched or modified.

## P1.3 status: CLOSED

`PAPER_AUTH = PASS`, `PAPER_ACCOUNT_QUERY = PASS`, `PAPER_OPEN_ORDER_QUERY = PASS`,
`ORDER_DISPATCH_WHEN_DISABLED = BLOCKED` -> `DOCKER_TECHNICAL_ACCEPTANCE = PASS`,
**`P1_3_CLOSED = YES`**.

The resource benchmark from the prior pass is preserved unchanged and is not rerun: Mode A (Host only)
system memory average 11,944 MB; Mode B (Hybrid) 13,545 MB; Mode C (Full Docker) 12,925 MB. Deltas:
Hybrid - Host = +1,601 MB; Full Docker - Host = +981 MB; Full Docker - Hybrid = -620 MB.
`CANONICAL_RUNTIME_DECISION` remains explicitly deferred -- this fix and its acceptance evidence do not
select a canonical runtime; that remains a separate, later decision.
