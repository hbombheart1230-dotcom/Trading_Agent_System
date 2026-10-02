# 2026-10-02 -- P1.3 R5: Docker healthcheck alignment, shutdown during lease wait, isolated recovery matrix

Code commit `61586ae`. No production state, Host process, Scheduled Task or `.env` was
touched; production Docker cutover has **not** been performed.

## R5-A -- Docker LIVENESS follows the canonical SQLite ownership heartbeat

`scripts/docker_healthcheck.py` judged LIVENESS by the lock-file heartbeat (rewritten only
at tick boundaries, 120s threshold) while R3 keeps the SQLite lease fresh from a
background thread. Legitimate ticks (p90 ~137s, max ~434s, closeout ~55 min) therefore
made a healthy runtime look unhealthy. LIVENESS is now: the canonical ownership row
exists, its lease is currently valid, and it names this container's runtime
(`owner_id` host == own hostname). Reasons are explicit (`source=sqlite_ownership
instance_id= generation= heartbeat_age_sec= lease_remaining_sec=`,
`no_valid_owner:lease_expired|no_owner_row`, `owner_is_other_runtime`,
`ownership_identity_mismatch`, `ownership_db_unreadable`).

The lock file is **diagnostic only**: missing, torn, or old heartbeats never fail the
check; the only lock-related failure is an explicit `ownership_identity_mismatch` when its
pid disagrees with the SQLite owner pid. The check is strictly read-only: SQLite is opened
in read-only URI mode (never creates/migrates/acquires/refreshes/releases), nothing else is
written, and the old `OWNERSHIP_STATUS` line, which used to construct the store (creating
the DB when absent), is read-only too. No new heartbeat, lease, ownership record or
generation authority; readiness semantics unchanged (EXECUTION_READY stays reported
separately and does not affect the exit code).

Known nuance (by design, documented): during a restarted container's bounded wait the old
instance's still-valid lease names the same `hostname:pid` (same container, PID 1), so the
check reports healthy-with-the-old-generation until takeover.

Tests: `tests/test_docker_healthcheck_ownership_liveness.py` (9): fake-time long tick
(lock heartbeat 500s old, SQLite fresh -> healthy), genuine loss / no row / other owner ->
unhealthy, mismatch observable and nothing mutated, byte-and-mtime read-only proof, missing
DB never created, acquire/refresh/release never called, plus a short real-time integration
with the actual `OwnershipHeartbeat`.

## R5-B -- shutdown request during R2's bounded wait

First tested as-is: it failed the contract. The shutdown handler was installed only after
ownership was acquired, so a SIGTERM during the wait hit Python's default action (instant
termination, PID lock left behind), and a flag-only shutdown still waited out the window
(exit 6) and would have taken ownership if the old lease expired afterwards. Fix (smallest):
the flag/handler is installed before the acquisition and the wait checks it before every
acquire attempt. The contender exits 0, never acquires (even if the old lease expires right
after the request), generation does not move, no heartbeat starts, no orphan thread, no tick,
and the PID lock it holds is released. Stale takeover with no shutdown request is unchanged.
Tests: `tests/test_m13_shutdown_during_lease_wait.py` (4, including a real SIGTERM via
`signal.raise_signal`).

## R5-D -- isolated Docker recovery matrix (image `trading-agent-20261002:61586ae`)

Isolated state root, no network, `--read-only`, user 10002, **no `init` (Python is PID 1)**,
`--restart on-failure:5`, mock executor with `EXECUTION_ENABLED=false`. The runtime path is the
real `m13_live_loop` wiring (`run_live_loop` + `run_m13_once` + the real readiness/recovery
nodes), with two pieces of test scaffolding in a harness file (not production code): the
tick clock is fixed to an in-session time (`MarketHours` is hard-coded 09:00-15:30 KST, so
after-hours ticks never reach the readiness node), and the documented
`state["portfolio_reader"]` / `state["open_order_reader"]` injection points supply an
isolated mock broker that can be made to fail until a flag file exists. Limits: the broker is
a mock, not the Paper server, and the production-state after-hours Docker test is still a
separate remaining step.

Observed (generations 1 -> 2 -> 3 -> 4; Docker `RestartCount` 0 throughout):

- gen 1: fresh GREEN readiness, healthcheck PASS.
- Hard crash (`docker kill`), restart inside the unexpired lease window with the mock broker
  down: the new PID-1 process got a new start identity (posix 12442562 -> 12444334) and R1
  reclaimed the lock (no `lock_active`); R2 logged `OWNERSHIP_WAIT_STARTED remaining_ttl_sec=24.6`
  and the process stayed alive while the old gen-1 lease stayed valid; takeover happened only at
  expiry (`OWNERSHIP_ACQUIRED_AFTER_WAIT generation=2`, ~25s). No storm.
- Recovery: right after takeover readiness showed `ready=False recovery_required=True
  reasons=[recovery_required, portfolio_reconciliation_invalid, open_order_reconciliation_invalid]`
  while liveness stayed PASS (EXECUTION_READY and liveness are separate). Once the mock broker was
  healed, the next tick's reconciliation inputs were all valid, `recovery_required` cleared only
  through the readiness node, and readiness went to fresh GREEN at generation 2. Step5D orphans 0.
- Controlled second restart (broker up): deterministic gen 3, GREEN on the first tick.
- Healthcheck across the cycle: healthy with a fresh owner, unhealthy with a still-valid lease
  held by another runtime (`owner_is_other_runtime`), unhealthy with an expired lease and no
  owner (`no_valid_owner:lease_expired`), healthy again after recovery (gen 4, GREEN).
- No order dispatch (0 executor artifacts, no mock positions/orders), mounts only the isolated
  state root, the production ownership row still `BOOK-P23MBGEMI1:12244` generation 1, the Host
  trading PIDs unchanged, no new Host live process.

No trading, UEF, Step5C or Step5D semantics changed.
