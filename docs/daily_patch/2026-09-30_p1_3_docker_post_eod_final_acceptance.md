# 2026-09-30 P1.3 Docker Post-EOD Final Acceptance Evidence (STILL OPEN)

## Scope

Final evidence collection only, against the frozen revision `68573419f1df90e07f9e7f4497d897d9ffc795fe`
and the isolated full-session soak started earlier today (documented in
`docs/daily_patch/2026-09-30_p1_3_docker_operational_acceptance.md`). No code, Docker configuration,
strategy, or execution-semantics changes in this pass. The real Host runtime was never touched, killed,
restarted, or signaled at any point.

## Soak evidence (startup through post-EOD)

- **Duration**: started 2026-09-30T00:29:36Z (09:29:36 KST) with a freshly reset isolated ownership
  lease; stopped cleanly via final SIGTERM at 2026-09-30T07:16:07Z (16:16:07 KST) -- roughly 6h47m.
- **Health/ownership**: `healthy`, `RestartCount=0`, `OOMKilled=false`, and an active ownership lease
  with a fresh heartbeat at every check throughout, including well after regular session close.
- **Memory**: only two real checkpoints were captured (this pass explicitly does not invent
  intermediate samples that were not actually polled) -- roughly 65 MiB shortly after startup, and
  roughly 159 MiB near the end of the run. The intermediate checkpoints requested (mid-session, pre-EOD,
  EOD-peak) were not proactively polled during the unattended window and are recorded as
  **NOT_CAPTURED**, not estimated. Memory pattern is classified **INSUFFICIENT_EVIDENCE** for that
  reason -- the two real points do not by themselves distinguish a stable plateau from gradual growth.
  Both values remain far below the 1 GiB container limit either way.
- **Tick activity stopped at regular session close**: the isolated soak's own event log shows continuous
  pipeline ticks (`route`/`route_selected`/`end`/`shadow_assessment`, one set roughly every 10s, 2,145
  ticks total) from startup through 2026-09-30T06:29:53Z (15:29:53 KST) -- essentially the entire regular
  session window -- and then stops. The lock file's heartbeat kept refreshing normally afterward (the
  container's own liveness check continued reporting `PASS` at every later check), and the final SIGTERM
  drained cleanly from an explicitly logged "idle sleep" state, not a stuck one. This is reported as a
  factual observation, not diagnosed at the source-code level (out of this pass's scope) -- it is
  consistent with, but not proven to be, the intraday-phase tick loop correctly quieting to a
  heartbeat-only idle mode once the regular session ends. The same activity-stops-at-15:30-KST pattern
  was also independently observed on the real Host runtime during this same window, which this pass
  never touched.

## EOD cascade: did NOT execute in the isolated soak

Concrete evidence, not inferred from the clock: the isolated soak's `data/state/kiwoom_market_status.json`
was never created (no live market-status feed exists in this isolated, `KIWOOM_MODE=mock` environment);
`persisted_state.processed_market_status_action_keys` never appears anywhere in the isolated `state.json`;
and a full scan of all 8,580 events in the soak's 53 MiB `events.jsonl` found zero occurrences of
`market_status_closeout`, `closeout_maintenance`, `regular_close`, or `final_refresh` -- the only stage
ever recorded was `commander_router`. The closeout trigger path (`apply_market_status_closeout_events`)
requires a real market-close status event to act on, and this isolated smoke environment structurally
cannot produce one. **EOD_CASCADE_EXECUTED = NO** for this soak.

## Production-sized EOD memory check (required, since the soak itself was small/isolated)

The soak's own event log (53 MiB, 8,580 events, a single hardcoded mock symbol) is not production-scale,
so a separate, bounded rehearsal was run per the required procedure: a fresh, isolated helper container
from the same frozen image, with a **read-only copy** (never a mount, never a write) of the real Host's
current `data/logs/events.jsonl` (≈770 MiB) and `data/state.json` (≈12 MiB) -- the canonical Host data
itself was never touched. `scripts/run_closeout_maintenance.py --skip-account-snapshot` was run once
against this copy with `EXECUTION_ENABLED=false`.

Result: completed cleanly in roughly 60-70 seconds, peak memory **≈321 MiB** (well under the 700 MiB
"good headroom" guidance), no OOM, no crash, full JSON report + evaluation artifacts produced. The
top-level result reported `"ok": false`, from 3 of 17 steps (`broker_closed_trade_reconciliation`,
`rank1_fixed_candidate_shadow`, `rank1_fresh_change_activation_shadow`) -- each a handled negative
result (`error: null`), matching the exact `SOURCE_MINUTE_HISTORY_MISSING`-class condition already
characterized in the prior closeout diagnostic hardening pass: expected for an isolated day with no real
upstream minute-history/broker connectivity, not a process failure. **PRODUCTION_SIZED_EOD = PASS.**

## Final SIGTERM and cleanup

`docker compose stop` completed in ~2.2s, exit code 0, `OOMKilled=false`; the lock file was removed
(ownership cleanly released) and the container's own log recorded a clean drain. The 770 MiB production
data copy used for the rehearsal was deleted immediately after use; it was never written to, and the
canonical Host files it was copied from were never touched. The frozen worktree and the soak's own
isolated evidence directory are left in place (not yet removed), per instruction.

## Paper broker connectivity: still PENDING

Not run. The real Host runtime (`EXECUTION_MODE=real`, `KIWOOM_MODE=mock`) remained actively running
throughout this entire pass, including live `market.minute_ohlcv` skill calls observed during this
evidence collection -- the precondition ("after the Host runtime is safely stopped or otherwise no
longer conflicts") was never met, and stopping the live Host runtime is outside this validation pass's
authority. Reported as `PENDING`, per the explicit fallback for this exact situation, rather than forcing
concurrent Host/Docker broker access.

## Status

DOCKER_OPERATIONAL_ACCEPTANCE = IN_PROGRESS (all core Docker mechanics passed; EOD cascade and paper
connectivity remain the two open items)
P1_3_CLOSED = NO
UEF_STATUS = COMPLETE / FORMALLY FROZEN (untouched)
CANONICAL_RUNTIME_DECISION = DEFERRED
