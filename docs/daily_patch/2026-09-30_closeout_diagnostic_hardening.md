# 2026-09-30 Closeout Diagnostic Hardening

## Scope

Observability-only. This does NOT fix the underlying closeout defects found while investigating the
2026-09-29 upstream gap -- it makes them diagnosable, per explicit instruction not to apply a behavioral
fix yet. No trading strategy, order/execution, UEF, or Docker semantics touched.

## Root-cause investigation findings (this session)

- **Tick-loop closeout path (`libs/runtime/market_status_closeout.py::apply_market_status_closeout_events`,
  called every tick from `graphs/pipelines/m13_live_loop.py::run_m13_once`) confirmed structurally silent
  on exception.** `run_m13_once`'s `except Exception as exc: state["market_status_closeout_error"] = ...`
  writes to a top-level `state` key -- but `graphs/nodes/save_state.py::save_state()` only ever persists
  `state["persisted_state"]`, a different key. Any exception caught here was **never written to disk
  anywhere**, confirmed as the reason `data/state.json`'s own `persisted_state.
  processed_market_status_action_keys` shows no recorded action since **2026-09-23**, despite valid
  `regular_session_close` (15:30 KST) and `after_hours_close_price_closed` (16:00 KST) events continuing to
  arrive in `data/state/kiwoom_market_status.json` every day since, including 2026-09-29.
- **Scheduled fallback (`TradingAgent-MockExamDay-Closeout`, weekdays 16:00 KST ->
  `scripts/run_mock_exam_closeout.bat` -> `scripts/run_closeout_maintenance.py`) failed with two different
  root causes on consecutive days**, confirmed via `schtasks` and the wrapper's own per-invocation log
  (`reports/runtime/closeout_maintenance_<date>_<time>.log`):
  - 2026-09-28: started 16:00:00.91, exited 16:10:37.26 (**~10m37s**), `rc=1`, with **zero captured
    stdout/stderr** -- the entrypoint's own `print()` calls only ever ran at the very end of `main()`, so a
    hang anywhere before that point left no trace of which stage it was in.
  - 2026-09-29: interrupted almost immediately (~2-3s) -- the log shows a literal `^C`; `schtasks` confirms
    `Last Result=-1073741510` (`0xC000013A`, `STATUS_CONTROL_C_EXIT`). Confirmed NOT systemic: four sibling
    scheduled tasks on the same day (Preopen, Q12-BTC-0855, Q12-Preopen, Session) all exited `0`. The task's
    `LogonType=InteractiveToken` is the most specific supported explanation (a process running under an
    interactive session receives a console/logoff control event if that session ends) -- not conclusively
    proven without host session-log access (Task Scheduler's own operational event log is disabled on this
    host).
- **2026-09-25's two failing steps (`rank1_fixed_candidate_shadow`, `rank1_fresh_change_activation_shadow`,
  `ok=False, error=None`) are a handled negative result, not a swallowed exception.** Traced to source: both
  steps set `"ok": bool(<builder>.get("ok"))` from a normally-returned dict, never from a caught exception --
  `error=None` was simply correct. The real explanation, found in the already-persisted report: both carry
  `day_status="SOURCE_MINUTE_HISTORY_MISSING"` -- the upstream opening-shadow builder itself could not obtain
  valid minute-level market history for that day (`libs/research/rank1_feature_mart/prospective.py`'s own
  status derivation: `elif opening_status != "VALID": status = f"SOURCE_{opening_status}"`).
- **`latent_reactivation` producer chain traced**: `build_opening_rank1_shadow()` (same function behind
  `opening_cumulative`, step `opening_rank1_prospective_shadow`) calls `build_latent_reactivation_watch()`
  which calls `build_latent_reactivation_forward()`, writing `latent_reactivation_forward.json`. It is not a
  separately-triggered source -- it shares `opening_cumulative`'s exact producer/caller/trigger, and
  therefore its exact failure mode on 2026-09-28/29 (the whole `run_closeout_maintenance` invocation never
  reached this step).
- **Zero-event persistence**: `libs/research/rank1_feature_mart/prospective.py` confirmed to have a genuine
  `VALID_NO_EPISODES` status path (persisted, not a silent no-write) -- the 2026-09-25 failure hit a
  different branch (`SOURCE_MINUTE_HISTORY_MISSING`, a real upstream-dependency gap, not a zero-event day).
- **No concurrency guard exists** between the tick-loop path and the scheduled fallback path -- both call
  `run_closeout_maintenance()` directly with no lock/idempotency mechanism. Confirmed
  `CONCURRENT_CLOSEOUT_POSSIBLE=YES`, `CLOSEOUT_SINGLE_OWNER_GUARD=ABSENT`. Not fixed in this pass --
  explicitly out of scope (behavioral fix).

## Diagnostic hardening applied

- `libs/runtime/market_status_closeout.py`: the `run_closeout_maintenance()`/`write_closeout_maintenance_report()`
  call is now wrapped in a log-then-re-raise handler -- exact same control flow (the exception still
  propagates to the same outer catch in `m13_live_loop.py`), but now writes a durable record (target day,
  event_id, code, action_key, trigger, exception type/message, full traceback) via the existing EventLogger
  (`data/logs/events.jsonl`, fsync'd on every write) before re-raising.
- `graphs/pipelines/m13_live_loop.py`: the outer `except Exception` backstop now also logs a durable record
  the same way, for anything not already logged closer to its source (e.g. a failure inside
  `load_market_status()` itself). `state["market_status_closeout_error"]` is unchanged -- kept, not replaced.
- `libs/reporting/closeout_maintenance.py`: new `log_closeout_stage()` helper (same EventLogger mechanism),
  called at `run_closeout_maintenance()`'s own start/end (with a full per-step ok/fail summary at the end) and
  at the start of the three stages most relevant to this investigation: `account_snapshot` (the step most
  likely to block on a real broker/network call) and the two steps behind the four daily UEF freshness
  sources (`opening_rank1_prospective_shadow`, `rank1_fixed_candidate_shadow`+
  `rank1_fresh_change_activation_shadow`). Deliberately bounded to these, not all 17 steps -- a diagnostic
  addition, not a full instrumentation framework.
- `scripts/run_closeout_maintenance.py`: full lifecycle logging (`process_start`, `closeout_start`,
  `closeout_end`, `report_write_start/end`, `scheduled_intelligence_start/end`, `process_exit`) plus a
  wrapping exception handler that logs the full traceback before re-raising -- so even an abrupt external
  termination (like 2026-09-29's) or a mid-run hang (like 2026-09-28's) now has an immediate, durable,
  flushed trail showing exactly how far the process got.

All new logging is additive-only (existing containment/control-flow unchanged), fails silently if the
EventLogger itself is broken (never masks or replaces the real exception being reported), and touches no
broker/order/execution code.

## Tests

`tests/test_closeout_diagnostic_hardening.py`, 9 passed: a caught tick-loop-path exception logs a durable
traceback with full context; the tick-loop's own outer backstop logs and preserves the existing
`market_status_closeout_error` field; the fallback CLI's lifecycle helper logs correctly on success and on a
simulated failure (verified to re-raise, matching existing exit-code behavior); diagnostic logging never
raises a secondary exception even when the underlying EventLogger itself is broken (3 cases); and none of the
new diagnostic helpers import any execution/broker/order module. Broader regression (closeout maintenance,
kiwoom market status, m13 live loop, daily UEF pipeline, patch notes, pytest hygiene): 67 passed.
`scripts/verify_uef_freeze_manifest.py`: 11/11 MATCH.

## Explicitly NOT done in this pass

No retry policy, no timeout changes, no scheduler re-registration, no trigger redesign, no source semantic
changes, no concurrency/locking fix, no UEF changes. The underlying closeout defects (why the tick-loop path
stopped recording since 2026-09-23; why the fallback hung on 2026-09-28; why it was terminated on
2026-09-29; the missing single-owner guard) remain open and are expected to be resolved in a separate,
bounded behavioral-fix pass, informed by whatever this instrumentation captures on the next occurrence.
