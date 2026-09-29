# 2026-09-30 Closeout Strict Owner-Identity Lock Fix (CRITICAL)

## Scope

CRITICAL runtime safety correction to the same-day closeout single-owner guard
(`docs/daily_patch/2026-09-30_closeout_single_owner_guard.md`). Independent of, and does not fix, the
still-unexplained 2026-09-28 closeout hang or 2026-09-29 `STATUS_CONTROL_C_EXIT` root causes. This pass
is scoped ONLY to lock ownership semantics -- no UEF, daily UEF publication, strategy semantics,
broker/order behavior, closeout business logic, or scheduler timing/retry policy touched.

## Confirmed defect

An independent audit found the first version of the closeout single-owner guard reused the shared lock
primitive's plain, age-based reclaim: a lock held past its staleness window (30 minutes) was reclaimed
even if its owner's PID was still genuinely alive. This meant a legitimately still-running closeout
could lose its own lock to a second trigger purely because it took longer than the staleness window --
a real runtime safety defect, since a real closeout run has already been observed to take ~10m37s
(2026-09-28). This risked exactly the concurrent-execution scenario the guard was built to prevent.

## Fix applied

`libs/runtime/live_loop_lock.py` -- `acquire_live_loop_lock()` and `release_live_loop_lock()` gain an
opt-in `strict_owner_identity` mode (Approach A: extend the existing shared primitive rather than build
a second, unrelated locking mechanism). All existing callers (the m13 live loop's own single-instance
guard) are unaffected -- strict mode is off by default and the non-strict code path is unchanged.

Under strict mode, enabled only for closeout:

- Ownership is proven by process identity (pid + a real OS process-creation timestamp), not by elapsed
  time. A live, identity-confirmed owner can never lose the lock merely because it has run a long time
  -- lock age is diagnostic metadata only, never a reason to reclaim.
- The process-creation timestamp comes from a genuine OS facility (not a self-recorded, driftable
  approximation), so a PID being reused by a different process after the original owner exits is
  correctly detected and distinguished from the original owner still running.
- A lock is only ever reclaimed when its owner is conclusively dead, or conclusively a different
  process (PID reuse). Two processes racing to reclaim the same dead owner's lock cannot both succeed --
  the reclaim decision is serialized through a short-lived guard step.
- Anything that cannot be conclusively verified -- corrupted lock data, or a live PID whose identity
  cannot be read -- is treated as "do not touch it" rather than guessed at or silently cleared.
- Releasing the lock now requires proof of the exact same ownership record that acquired it; a process
  can never delete a lock it does not actually own, even if the lock file changed underneath it.

`libs/reporting/closeout_maintenance.py` -- the closeout single-owner wrapper now uses strict mode, with
richer ownership diagnostics (why an acquisition succeeded/failed, lock age as diagnostic-only metadata,
release outcome) recorded through the same durable failure log added in the prior closeout diagnostics
update. Both trigger paths (the live tick-loop and the scheduled fallback) already called this wrapper
and required no further changes to pick up the fix.

## Tests

`tests/test_closeout_single_owner_guard.py` rewritten, 25 tests covering the full required matrix:
live owner younger and OLDER than the staleness threshold (the direct regression test for this fix --
an older-than-threshold live owner must still block a second attempt), dead-owner and PID-reuse
reclaim, wrong-token and wrong-identity release rejection, malformed lock and unverifiable-identity
fail-closed (no silent deletion), guarded concurrent reclaim (no double reclaim), exception-path
release, later retry after failure or crash, and end-to-end integration proving both trigger paths
(tick-loop and scheduled fallback) are wired to the corrected strict semantics -- not just the
underlying function in isolation. The old test that proved the bug (a long-running-but-live lock being
reclaimed) is removed and replaced by its opposite. All synchronization is deterministic (ownership
metadata written/backdated directly) -- no sleep- or thread-based timing tests.

Full regression: 11 pre-existing failures confirmed unrelated and identical to the unmodified tree
(none touch closeout, market-status, or lock code). `scripts/verify_uef_freeze_manifest.py`: 11/11
MATCH.

## Explicitly NOT done in this pass

No fix or speculation about the 2026-09-28 hang cause, the 2026-09-29 `STATUS_CONTROL_C_EXIT` cause, or
scheduler `LogonType`. No timeout/retry policy. No scheduler registration or modification. No UEF,
strategy, or execution semantics changed. No second locking framework introduced -- the existing shared
primitive was extended, not replaced.

This fix has not yet been independently re-audited. Do not trigger the real scheduled closeout until
that review is complete.
