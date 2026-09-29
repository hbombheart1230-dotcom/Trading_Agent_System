# 2026-09-30 Closeout Single-Owner Guard

## Scope

Bounded runtime safety fix -- independent of, and does not claim to fix, the still-unexplained
2026-09-28 closeout hang or 2026-09-29 `STATUS_CONTROL_C_EXIT` root causes documented in the prior
closeout diagnostic hardening pass. This pass implements ONLY a single-owner / idempotent closeout
execution guard, per explicit instruction. No trading strategy, order/execution, scheduler
registration, retry/timeout policy, or UEF semantics touched.

## Confirmed defect (from the prior diagnostic hardening pass)

The tick-loop closeout trigger (`libs/runtime/market_status_closeout.py::apply_market_status_closeout_events`,
called every tick from `graphs/pipelines/m13_live_loop.py`) and the scheduled fallback CLI
(`scripts/run_closeout_maintenance.py`, invoked by `TradingAgent-MockExamDay-Closeout`) both called
`run_closeout_maintenance()` directly, with no coordination between them. Nothing prevented both from
executing concurrently and writing the same dated report/artifact paths at the same time
(`CONCURRENT_CLOSEOUT_POSSIBLE=YES`, `CLOSEOUT_SINGLE_OWNER_GUARD=ABSENT`).

## Fix applied

- `libs/reporting/closeout_maintenance.py`: new `run_closeout_maintenance_with_lock()` wrapper --
  the function both trigger paths now call, never `run_closeout_maintenance()` directly. It reuses
  this repository's existing PID-based lock primitive (`libs/runtime/live_loop_lock.py`, already used
  and proven for the m13 live loop's own single-instance guard) rather than inventing a second,
  unrelated locking mechanism.
  - Acquire-before-run, release-in-`finally` -- released on both normal completion and any exception,
    so a later, separate, explicit invocation is never permanently blocked by an earlier failure.
  - A live owner's lock is respected (`lock_active` -> reject); a genuinely DEAD owner's lock (real
    Windows/POSIX process-existence check) is reclaimed automatically; a lock held past a 30-minute
    staleness window is also reclaimed even if its PID happens to still exist. The 30-minute window is
    a wide safety margin above the one anomalous closeout duration on record (~10m37s, 2026-09-28) --
    it is the lock's own staleness window, not a retry/timeout policy for the underlying closeout
    defects, and no automatic retry is performed anywhere in this guard.
  - A rejected attempt returns a clearly-marked `skipped=True, skip_reason="ALREADY_RUNNING"` result
    without ever calling `run_closeout_maintenance()`.
  - Ownership acquire/reject/release is logged via the existing `log_closeout_stage()` EventLogger
    helper added in the prior pass (not a new logging mechanism), including trigger, target day,
    lock path, and owner/requesting pid -- reject events also record the active owner's pid when
    available.
- `libs/runtime/market_status_closeout.py`: the tick-loop trigger now calls
  `run_closeout_maintenance_with_lock()` instead of `run_closeout_maintenance()` directly. A skipped
  (`ALREADY_RUNNING`) result does not write a report -- writing one here could race against whatever
  the real owner is concurrently writing to the same dated path. The event is still marked processed
  (so it is not redelivered), but the action itself is deliberately NOT marked processed, so a later
  tick (once the real owner's lock is free) can still complete the closeout rather than being
  permanently skipped by a one-time lost race.
- `scripts/run_closeout_maintenance.py`: the fallback CLI now calls the same guarded wrapper. A
  skipped result likewise does not write a report or run scheduled intelligence, and is treated as a
  clean outcome (exit code 0), not a failure -- distinguishable from a real failure via the existing
  `--json` output's `skipped` / `skip_reason` fields and lifecycle log.
- Existing diagnostic instrumentation from the prior pass (durable tracebacks, stage-boundary logging)
  is unchanged.

## Tests

`tests/test_closeout_single_owner_guard.py` (new, 12 tests): two simulated concurrent triggers ->
exactly one enters closeout, the other returns a safe `ALREADY_RUNNING` result without ever calling
the underlying closeout function; normal completion releases the lock (verified by a subsequent
successful acquire); an exception during the guarded call still releases the lock; a dead-owner lock
and a stale-but-live-pid lock are both reclaimed; a later explicit retry after an earlier failure is
permitted; both trigger paths skip writing a report when ownership is rejected; the guard function
imports no broker/order/execution module. All synchronization is deterministic (PID injection /
hand-written lock files) -- no sleep-based timing tests.

`tests/test_closeout_diagnostic_hardening.py` updated (one test's monkeypatch target changed from
`run_closeout_maintenance` to `run_closeout_maintenance_with_lock` to match the new call path; no
behavioral change to the test itself).

Full regression: 12 pre-existing failures confirmed unrelated (identical on the unmodified tree, or
order-dependent flakiness that passes in isolation both before and after this change) -- none touch
closeout, market-status, or lock code. `scripts/verify_uef_freeze_manifest.py`: 11/11 MATCH.

## Explicitly NOT done in this pass

No fix or speculation about the 2026-09-28 hang cause, the 2026-09-29 `STATUS_CONTROL_C_EXIT` cause,
or scheduler `LogonType`. No timeout/retry policy. No scheduler registration or modification. No UEF,
strategy, or execution semantics changed. No second locking framework introduced.
