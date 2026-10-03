# 2026-09-30 P1.3 Integrated EOD Cascade Attempt (Result: Still Pending)

## Scope

Final evidence collection only, against the frozen revision `68573419f1df90e07f9e7f4497d897d9ffc795fe`.
No code, Docker configuration, strategy, or execution-semantics changes. The real Host runtime was never
touched, killed, restarted, or signaled. UEF was not touched.

Per instruction, this pass did not repeat the already-passed items (source parity, startup/health,
ownership/double-runtime, Step5C/Step5D, state persistence, crash/restart, the 6h47m soak, or the
production-sized EOD memory rehearsal) -- those remain authoritative from the prior two patch notes.

## Integrated EOD cascade attempt

Before writing any new fixture logic, the frozen runtime was inspected for an already-supported way to
drive the normal closeout path with synthetic market-status input. One was found:
`libs/runtime/kiwoom_market_status.py::record_market_status_events()` -- the exact same function the real
`KiwoomMarketStatusListener` calls internally when a genuine websocket message arrives. It was invoked
directly (via `python -c`, no file changes) in a fresh isolated container from the frozen image, with a
schema-correct synthetic `regular_session_close` (code `4`) event, matching exactly what
`parse_market_status_messages()` would have produced from a real message. This writes
`data/state/kiwoom_market_status.json` through the unmodified production writer -- the same file
`apply_market_status_closeout_events()` reads on every tick via `load_market_status()`.

Also confirmed by inspection: `graphs/pipelines/m13_live_loop.py::run_m13_once()` calls
`apply_market_status_closeout_events()` unconditionally on every tick (not gated by market hours at that
level), wrapped in a bare `except Exception: state["market_status_closeout_error"] = ...` that is never
persisted to disk (`save_state()` only persists `persisted_state`) -- this is the exact same
diagnostic gap already characterized and durably logged in this session's earlier closeout diagnostic
hardening work, still present (unmodified, as expected) at this earlier frozen SHA.

**Result: inconclusive.** After the synthetic event was written, the isolated container was observed for
several tick cycles (well beyond its own `--sleep-sec 10` cadence). No `commander_router`-stage events
(the stage the working 6h47m soak showed continuously during real session hours) appeared at all in this
fresh container's event log, `persisted_state.kiwoom_market_status` was never populated, and
`persisted_state.processed_market_status_event_ids`/`processed_market_status_action_keys` remained unset.
Calling `run_closeout_maintenance()` directly (bypassing the tick loop entirely) completed normally with
no exception, so the underlying closeout function itself is not the blocker.

This is reported as-is, not root-caused further -- diagnosing exactly which tick-pipeline wiring the
running container's `--tick-pipeline integrated_chain` mode actually exercises, and whether/how it differs
from the `run_m13_once` wiring read above, is a source-level investigation outside this evidence-collection
pass's scope ("do not create new runtime behavior merely to close P1.3"). The container itself remained
healthy throughout (`OOMKilled=false`, `RestartCount=0`, clean exit 0 on stop) -- this is not a crash or
resource issue, only an unconfirmed cascade trigger.

**EOD_CASCADE = PENDING.** What would resolve it: either (a) observe a real Kiwoom market-close status
event processed during an actual live regular trading session by the frozen image (the genuine listener
path, not a synthetic write), confirmed via `processed_market_status_action_keys` populating and a
`closeout_maintenance` report artifact appearing; or (b) a separately scoped, explicitly authorized
investigation into which tick-pipeline implementation governs `--tick-pipeline integrated_chain` and
whether it invokes `apply_market_status_closeout_events()` the same way `run_m13_once` does.

## Frozen-SHA Kiwoom Paper connectivity: still PENDING

Unchanged from the prior pass. The precondition ("Host runtime safely stopped, no ownership/state
collision") was not met -- the real Host runtime remained actively running throughout this entire pass
in a Paper-Trading-adjacent configuration (`EXECUTION_MODE=real`, `KIWOOM_MODE=mock`). Stopping the live
Host runtime is outside this validation pass's authority and was not done.

## Status

P1_3_CLOSED = NO (both remaining closure items -- EOD_CASCADE and frozen-SHA Paper connectivity -- are
still open)
UEF_IMPLEMENTATION = COMPLETE / FROZEN (untouched)
UEF_P1_1 = PASS / CLOSED
UEF_P1_2 = ACTIVE / DAILY CROSS-DAY OBSERVATION
CANONICAL_RUNTIME_DECISION = DEFERRED
