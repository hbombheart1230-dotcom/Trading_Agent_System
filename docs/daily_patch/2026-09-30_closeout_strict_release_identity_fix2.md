# 2026-09-30 Closeout Strict Release-Identity Fail-Closed (Fix2, CRITICAL)

## Scope

Same-day follow-up correction to `docs/daily_patch/2026-09-30_closeout_strict_owner_lock_fix.md`. Scoped
ONLY to the release-side identity check in the strict-owner lock primitive. Independent of, and does not
fix, the still-unexplained 2026-09-28 hang or 2026-09-29 `STATUS_CONTROL_C_EXIT` root causes. No UEF,
strategy, broker/order, or closeout business logic touched. No change to acquisition/reclaim logic and no
change to the non-strict m13 live-loop code path.

## Confirmed defect

An independent audit found one remaining unsafe branch in strict-mode release
(`libs/runtime/live_loop_lock.py::release_live_loop_lock`): the check
`if my_identity and existing_identity and my_identity != existing_identity: reject` is falsy -- and so
silently falls through to deleting the lock -- whenever `my_identity` is `None`, i.e. exactly the case
where this process's own identity could not be verified at release time. An unverifiable identity is not
proof of ownership and must never be treated as a free pass to release.

## Fix applied

Release under `strict_owner_identity=True` now requires a positive, verified match of all three fields
(pid, process_start_identity, owner_token):
`if not my_identity or not existing_identity or my_identity != existing_identity: reject`. A missing or
unverifiable identity on either side -- the caller's own, or the value recorded in the lock file -- now
fails closed and preserves the lock, matching the fail-closed principle already applied on the
acquisition side.

## Tests

`tests/test_closeout_single_owner_guard.py`: added
`test_t6b_release_with_unverifiable_own_identity_fails_closed` (own identity mocked to `None` during
release -> release rejected, lock file byte-identical afterward). Full closeout/lock/m13 regression
re-run: 80 passed. `scripts/verify_uef_freeze_manifest.py`: 11/11 MATCH. No repo-local pytest scratch
leftovers.

## Explicitly NOT done in this pass

No change to acquisition/reclaim logic, closeout business logic, UEF, or the non-strict m13 code path.
Not yet independently re-audited -- do not trigger the real scheduled closeout until that review is
complete.
