# 2026-10-02 -- P1.3 R1-R4: Docker restart safety and Host/Docker runtime-mode gate

Docker is **not yet** the canonical trading runtime. The Host runtime traded and
closed out normally today (see "Host session" below) and is still running; none of
the changes below touch the production Host process, the production ownership row,
or any Windows Scheduled Task. Everything here is code + tests, committed and pushed;
the production cutover itself is a separate, later step.

## Why: two restart-storm layers behind the 2026-10-01 Docker incidents

The 2026-10-01 production Docker runtime crashed twice and was left `Exited` because
`--restart=on-failure:5` exhausted its budget in seconds. Two independent age-based
gates were responsible; fixing only the first still storms (found in the P1.3-R1
controlled restart validation):

1. **M13 PID file lock (R1).** Docker gives the app a deterministic low PID (PID 1 in
   production, which has no `init`) in a fresh namespace each restart. The old
   non-strict `acquire_live_loop_lock` only reclaimed a lock once it was older than
   `lock_stale_sec` (300s), so a restarted container saw the dead predecessor's PID-1
   lock as a live owner (`lock_active`, exit 4) on every sub-second retry.
2. **SQLite ownership lease (R2).** `SQLiteRuntimeOwnershipStore.acquire()` correctly
   refuses a still-valid lease held by another instance; `run_live_loop` then exited 6
   immediately, faster than the killed owner's 30s lease could expire.

## R1 -- strict process identity for the M13 lock (`f792dcf`)

`run_live_loop` now uses the existing `strict_owner_identity=True` mode (the same
primitive closeout already uses; no second lock subsystem). Ownership is proven by
pid + OS process-start identity + owner token, never by age: a dead owner or a reused
PID (same number, different start identity) is reclaimed on the first attempt; a live
identity-matched owner is never stolen; an unverifiable identity fails closed; release
requires the exact owner. `refresh_live_loop_lock` gained its own strict branch (it had
none: calling it in strict mode would have overwritten the strict fields with the old
heartbeat schema every tick) and writes via tmp+`os.replace` (a plain `write_text` let
`docker_healthcheck.py` read a torn file and report `LIVENESS=FAIL`).

## R2 -- bounded ownership wait (`747b841`)

`_acquire_ownership_with_bounded_wait`: on `owned_by_other_instance` the caller waits,
bounded by the rejected lease's own observed `lease_expires_at` plus a 5s margin (no
second hardcoded lease duration), then retries; once the lease genuinely expires the
store's unchanged stale-takeover path performs the transition. Still valid at the end
of the window -> `OWNERSHIP_WAIT_TIMEOUT`, fail closed. The store is untouched; a valid
lease is never stolen.

## R3 -- background ownership heartbeat (`4c4d210`)

Ownership was refreshed only at tick boundaries, but ticks ran median ~36s / p90 ~137s
/ max ~434s, and the 15:30 closeout tick ran ~55 minutes, against a 30s lease: a live,
healthy owner routinely looked stale and a contender's stale takeover could have
succeeded mid-tick. `OwnershipHeartbeat` refreshes the same existing lease from a daemon
thread started only after ownership is acquired and stopped (joined) before the lock and
lease are released. Interval = lease/3 (derived from the lease config; an override must
be < lease). It only calls `store.refresh()` (CAS keyed on this `instance_id`), so a
superseded owner can never be resurrected; generation is also compared. Loss, or no
successful refresh for a full lease, marks the runtime unsafe and the loop exits 7
before the next tick (an in-flight tick is never interrupted). A crash kills the thread
with the process; the lease expires and R2 applies unchanged.

Two pre-existing tests encoded pre-R2/R3 behavior and were updated with their safety
intent preserved (`test_p0d_runtime_ownership.py`, `test_p0d_cutover_rollback_simulation.py`):
a valid foreign lease is still never displaced and nothing dispatches (now after the
bounded wait, using a short refreshed lease instead of a 60s lease with a no-op sleep that
busy-spun for 65s); and mid-loop ownership loss still exits 7 (modelled as a fully
stalled process, since a live process can no longer lose its lease to a long tick).

## R4 -- `TRADING_RUNTIME_MODE=host|docker` (`c2a2e75`)

The Windows tasks `TradingAgent-MockExamDay-Session` (weekdays 09:00) and
`TradingAgent-MockExamDay-SessionWatchdog` (09:05, every 5 min to 15:25) run
`start_trading_day.py`, which starts the Host M13 live loop **and** the Q10/Q11/Q12,
opportunity-engine and macro collectors that feed the Daily UEF freshness contracts, so
the tasks cannot simply be disabled. `libs/runtime/runtime_mode.py` is one explicit
configuration switch (process env, then the repo `.env`, default `host`):

- `host`: current behavior, unchanged.
- `docker`: only the Host live launch is skipped, logging
  `HOST_LIVE_START_SKIPPED_CANONICAL_RUNTIME_DOCKER`; collectors/shadow loops are ensured
  exactly as before, the watchdog makes no Host live-recovery decision and does not
  touch the Host supervisor state, and the Host live loop's absence is not a blocker.
- any other value: also skips the Host launch (`..._RUNTIME_MODE_INVALID`), so a typo
  can never re-enable a second mutation-capable runtime.

Configuration only: it never inspects Docker or Host PID liveness and gates launch only;
the SQLite lease stays the sole dispatch authority. `restart_live_session.py` (the only
launcher of `run_session.py --mode live --phase intraday`, verified by a repository scan
test) returns before its stop-stale-session / lock-removal step in docker mode. Rollback
= set `TRADING_RUNTIME_MODE=host`. **The key is not set in `.env` yet; the default is
`host`, so tomorrow's tasks behave exactly as before until the cutover sets it.**

## Host session and Host autostart RCA (read-only findings, 2026-10-02)

- The Host runtime was launched at 09:00:05 by the weekday Windows task
  `TradingAgent-MockExamDay-Session` -> `run_mock_exam_session.bat` ->
  `start_trading_day.py --mode start` -> `restart_live_session.py` -> `run_session.py`;
  LastRun 09:00:00 matches. The Watchdog task is a second launcher. No Run-key, Startup
  folder, service or WMI launcher exists. PID 28380 (venv `python.exe` stub) and PID
  12244 (real interpreter) are one logical runtime, not a duplicate; ownership stayed at
  generation 1 all day with zero error events.
- Trading: one completed round trip, 233740 BUY 91 @ 8240 / SELL 91 @ 8195, realized
  about -9,325 KRW; no residual position, no open order, 0 Step5C claims, 0 Step5D orphans.
- Closeout: the 15:30:14 market-status closeout ran ~55 minutes and succeeded; the 16:00
  scheduled fallback was rejected `ALREADY_RUNNING_VALID_OWNER` (it fired mid-run, 30
  minutes past the old stale window -- the exact case the strict lock protects); a later
  market-status code skipped `ALREADY_COMPLETE`; exactly one durable SUCCESS record.
- Daily UEF 16:45: the S4U task fired at 16:45:01 (on schedule), result 0, START/END logs
  present, exactly one COMPLETE generation `UEF9RUN_d9a47e5fd0f019bb` (UEF7/8/9 valid),
  `current`/`latest`/registry consistent.
- `execution_readiness` is only produced while `MarketHours` (hard-coded 09:00-15:30 KST)
  considers the market open; after hours every tick is a skipped no-op, so a Docker
  runtime started after hours will not produce fresh readiness on its own.

## Verification

Focused tests (R1 matrix, R2 lease wait, R3 heartbeat, R4 mode gate, ownership, closeout
guard/completion, graceful shutdown, crash matrix, launcher/watchdog, Step5C/5D,
ExecutionReadiness) pass. Pre-existing `test_step5b_*` environment-dependent failures are
not touched (confirmed on the old frozen baseline for `test_step5b_fix4.py`; I did not trace every one). `test_pytest_artifact_hygiene` fails
only while the Host live loop is running (its audit flags the Host's own lock/ownership
writes). No trading, UEF, Step5C or Step5D semantics changed.
