# 2026-10-01 -- HOST Runtime Pivot: Final Ops Cleanup

## Decision of record

**Canonical trading runtime: HOST.** Docker trading (`trading-agent-live` container,
built from the 2026-10-01 P1.3-accepted image `trading-agent-20261001:025a16a4`) is
**not adopted** for ongoing production use.

This is explicitly **not** a claim that Docker trading was technically impossible --
P1.3 operational acceptance (see `2026-09-30_p1_3_closed_read_write_gate_fix.md` and
the preceding P1.3 patch notes) proved it functionally viable: frozen-SHA image
build/parity, isolated smoke, a 6h47m soak, a production-sized EOD memory
rehearsal, and Paper broker read connectivity all passed, and the real 2026-10-01
cutover ran genuine canonical trading activity in Docker for several hours. The
reason for reverting to Host is **operational**: production lifecycle/restart
complexity (see "Second incident occurrence" below) provides insufficient benefit
over Host for the current single-machine deployment. The 2026-10-01 Docker incident
RCA (first occurrence, manually recovered) remains preserved as historical
evidence/backlog -- not erased, not superseded by this decision.

## Second Docker incident occurrence (today, same root cause, NOT manually recovered)

During this cleanup pass, `docker ps -a` showed `trading-agent-live` as
`Exited (4)` since **2026-10-01 08:47:45 UTC (17:47:45 KST)** -- roughly 50 minutes
before this check. Container logs show the exact same failure mode already
root-caused earlier today (PID-1-always-alive-in-a-fresh-container-namespace racing
Docker's sub-second `--restart=on-failure:5` backoff against the 300s lock
staleness window): repeated `live_loop lock not acquired: lock_active` lines
interleaved with `acquired ownership via stale takeover` lines at generations
2->3->4->5, each cycle lasting well under a second
(`StartedAt=2026-10-01T08:47:44.956597844Z`, `FinishedAt=2026-10-01T08:47:45.241958444Z`
for the final cycle), until the restart budget was exhausted. Unlike the first
occurrence (manually recovered via `docker start` once the staleness window had
naturally elapsed), this second occurrence was left as-is per this task's explicit
instruction not to revalidate or fix Docker trading now. This is corroborating,
not new, evidence for the HOST pivot decision -- not an additional root cause.

**Per the explicit instruction in this task: the Docker PID-1/M13 restart fix is
BACKLOGGED, not implemented now.**

## Current live-runtime state (read-only verification, see FINAL OUTPUT for full detail)

Neither Docker nor Host currently holds a live, unexpired M13 live-loop ownership
lease. `data/state/m13_live_loop.lock` on the shared canonical filesystem still
shows `"pid": 1` (Docker's own container-namespace PID) from the last stale-takeover
cycle before the container's final exit; no Host `python.exe` process is currently
running. This is expected/acceptable for today (market closed at 15:30 KST, and all
EOD closeout/Daily-UEF obligations for 2026-10-01 completed successfully on Host --
see below) but means **the Host-side M13 live loop has not yet been started today**
and must be started before the next trading session. The existing stale/dead-owner
reclaim logic in `libs/runtime/live_loop_lock.py` (unmodified) is expected to clean
up the stale Docker-origin lock automatically on Host start -- PID 1 does not
resolve to a live process from the Host's own process table, so this is the
ordinary dead-owner-reclaim path, not a new code path.

## Closeout durable-completion authority (new, additive)

Added `libs/reporting/closeout_completion_authority.py`: a small, standalone,
SUCCESS-only durable marker keyed by `target_day:action_key`
(`action_key` = `daily_closeout_maintenance`, shared across both trigger paths --
see the module's own docstring for why this is a single logical unit of work
regardless of which specific code/trigger caused it to run). Consulted by
`run_closeout_maintenance_with_lock()` (in `libs/reporting/closeout_maintenance.py`
-- the single entrypoint both `libs/runtime/market_status_closeout.py` and
`scripts/run_closeout_maintenance.py` already call) **before** attempting the lock
at all; written **only** after `run_closeout_maintenance()` returns `ok=True`.

This is deliberately **separate** from the existing strict-identity lock
(`libs/runtime/live_loop_lock.py`), per explicit instruction not to overload the
lock with both meanings: the lock answers "is someone else running this right
now"; the new primitive answers "has this already successfully finished" -- a fact
the lock cannot represent on its own, since it is released on both success and
crash/failure alike. Real-world motivation found during this session's own
investigation: today's `reports/operator_summary/daily/2026-10-01/closeout_maintenance.json`
(`ok: true`, `trigger: "scheduled_closeout_fallback"`, written 16:33 KST) was
followed by a second wave of downstream artifact writes (`daily_summary`,
`operator_summary`, `q8_shadow_blocker_review`, `q9_decision_windows`) at
17:44-17:45 KST that did **not** rewrite `closeout_maintenance.json` itself --
consistent with, though not definitively proven to be, a second full closeout
attempt for the same day. This fix prevents exactly that class of redundant
re-run once the currently-running Host process is restarted with this change.

Tests: `tests/test_closeout_durable_completion_authority.py` (8 new tests, A-F
per spec plus day-isolation and a structural no-execution-import check).
`tests/test_closeout_single_owner_guard.py` was updated to pass its own
`tmp_path`-scoped `completion_authority_path` to every direct
`run_closeout_maintenance_with_lock()` call (mirroring its existing `lock_path`
convention) -- without this, the new completion check's *default* path, while
correctly isolated away from the real repository under pytest via
`libs/core/path_isolation.py::resolve_runtime_write_path`, is still shared across
the whole pytest *process*, so same-day tests without their own override would
otherwise short-circuit each other. Also fixed two pre-existing, unrelated
hardcoded-date test fixtures (`test_t12a_...`, `test_market_status_trigger_skips_report_write_when_ownership_rejected`)
that silently broke once real wall-clock time moved past 2026-09-30 -- confirmed
via a true-baseline run against the unmodified `HEAD` version of
`closeout_maintenance.py` that these two failures pre-date this change and are
unrelated to it. All 34 tests across both files pass.

## Daily UEF entrypoint durable observability logging (new, additive)

`scripts/run_daily_uef_evaluation.py` (clean/untouched by any other in-progress
work in this tree -- verified via `git status` before editing) now emits
START/END lifecycle events via the existing `EventLogger`
(`data/logs/events.jsonl`), mirroring `scripts/run_closeout_maintenance.py`'s own
established `_log_lifecycle` pattern exactly rather than inventing a new one.
Start: `target_day`, `pid`, `started_at_epoch`, `source_sha` (`git rev-parse HEAD`,
best-effort -- never fails the run if git/.git is unavailable), `canonical` flag.
End: `ended_at_epoch`, `result` (`ok`/`failed`/`exception`), `exit_code`,
`canonical_generation` (the UEF-9 `authority_id`), `failure_reason`. This is
independent of, and does not replace, Windows Task Scheduler's own run history
(`LastRunTime`/`LastTaskResult`), and does not duplicate UEF authority itself --
`COMPLETE.json` remains the sole authority for whether a day's evaluation is
valid; these events exist to diagnose a run that crashed or hung before ever
reaching that point, which `COMPLETE.json`'s mere absence cannot explain on its
own. Verified via a `--diagnostic` dry run (writes no canonical file, confirmed by
its own pre-existing contract) with `EVENT_LOG_PATH` redirected to an isolated
scratch file -- exit 0, both lifecycle events captured correctly including the
real current `source_sha`.

## 2026-10-01 UEF9 generation provenance (`UEF9RUN_e1c4ae6eab1ecaad`)

Investigated per this task's explicit instruction before assigning any status.
`reports/evaluation/alpha_research_board/2026-10-01/generations/UEF9RUN_e1c4ae6eab1ecaad/COMPLETE.json`:
`status: COMPLETE`, `uef9_authority_status: VALID`, `generated_at` (epoch
1790844139.3) converts to **2026-10-01 17:42:19 KST**. `Get-ScheduledTaskInfo` for
`TradingAgent-DailyUefEvaluation` showed `LastRunTime: 2026-10-01 17:42:15`,
`LastTaskResult: 0` (success) -- matching within 4 seconds. The task's own
`Action` (`python.exe scripts/run_daily_uef_evaluation.py`,
`WorkingDirectory=C:\Trading_Agent_System`) matches the legitimate production
entrypoint exactly. `p1_2_daily_observation_registry.json` carries a consistent
`2026-10-01` entry for this same `authority_id`, and `latest.json` points at it
with no conflicting pointer.

**Conclusion: this is a genuine, normal canonical daily pipeline run, dispatched
by the legitimate Windows Scheduled Task -- not a manual operator run, not an RCA
subprocess, not another process.** `EVALUATION_OBSERVATION: VALID`. However,
`SCHEDULED_AUTOMATION` for today is **PASS-BUT-LATE**, not a clean on-time pass:
the task fired ~57 minutes after its configured `16:45:00` `StartBoundary`. This
delay is the direct symptom explained by the Scheduled Task hardening below (see
next section) -- `LogonType=Interactive` means the task can only fire while an
interactive desktop session is active, and is exactly the kind of gap that
produces a late-but-eventually-successful run rather than a clean on-time one.

## Windows Scheduled Task hardening (`TradingAgent-DailyUefEvaluation`)

Audited principal, logon type, battery restrictions, non-interactive safety,
working directory, executable path, arguments, multiple-instance policy, and
missed-run behavior. Applied, with the user's explicit confirmation:

- **`DisallowStartIfOnBatteries` / `StopIfGoingOnBatteries`: True -> False**
  (applied, verified via `Get-ScheduledTask`). Irrelevant-to-harmless on a desktop
  trading machine; removes a silent-skip risk with zero error trace if this is
  ever run on battery power.
- **`LogonType`: Interactive -> S4U** -- identified as the most likely root cause
  of today's (and any prior) late/missed trigger: Interactive logon requires an
  active desktop session, so the task simply cannot fire at all until one exists.
  **Not yet applied** -- `Set-ScheduledTask -Principal` for a logon-type change
  requires an elevated (Administrator) PowerShell session; the working session is
  not elevated (`Access is denied`, confirmed via `whoami /groups` showing
  Administrators as "deny only"). Exact command for an elevated session, and a
  background task chip to track it, were handed to the user:
  ```
  $task = Get-ScheduledTask -TaskName "TradingAgent-DailyUefEvaluation"
  $newPrincipal = New-ScheduledTaskPrincipal -UserId $task.Principal.UserId -LogonType S4U -RunLevel Limited
  Set-ScheduledTask -TaskName "TradingAgent-DailyUefEvaluation" -Principal $newPrincipal
  ```

No weakening of credential/security requirements: `RunLevel` stays `Limited`
(standard user, not elevated); `MultipleInstances=IgnoreNew`,
`StartWhenAvailable=True`, working directory, Python executable path (project
venv), and arguments (no `--diagnostic`, per the script's own explicit
scheduler contract) were all confirmed already correct and left unchanged.

## Temporary worktree cleanup (confirmed complete)

`C:\Trading_Agent_System_p1_2_fix` and `C:\Trading_Agent_System_p1_2_final` --
both fully gone (the previously-blocked empty residual directory for
`..._p1_2_final` is no longer present; the OS appears to have released it since
the prior check). `git worktree prune -v` found nothing stale to prune; both
branches (`codex/p1-2-idempotency-fix`, `codex/p1-2-final-integration`) remain
intact. No new temporary worktree was created for this task.

## Docker storage cleanup (scoped)

Removed, as this session's own now-superseded P1.3 acceptance-testing images
(confirmed via `docker ps -a` that no container, running or exited, referenced
any of them): `trading-agent-p13-fix:11c7e3c`, `trading-agent-mock-runtime:local`,
`trading-agent-p13-frozen:68573419`, `trading-agent-real-runtime:local`
(~1.9GB reclaimed). **Left untouched, pending the user's own review**: the exited
`trading-agent-live` container and its image `trading-agent-20261001:025a16a4`
(today's real production cutover artifact -- a second genuine incident, see
above); `trading-agent-observability-web:test` (not created by this session, no
context on its purpose); the three running observability containers
(`cloudflared`, `web`, `api` -- explicitly out of scope, a separate future
migration item per this task's own instructions, not to be mixed into this
cleanup).

## What remains frozen / untouched

UEF core, UEF7/8/9 semantics, Step5C, Step5D, trading strategy semantics,
Scanner, Strategist, Executor semantics -- not modified. The concurrent,
unrelated "P1.2 Daily UEF Automation Integration" work already sitting
uncommitted in this tree (`apps/operator_ui/data_access_core.py`,
`deploy/m28_launch_templates/windows/daily_uef_evaluation_task.xml`,
`docs/milestones/UEF.md`, `libs/reporting/evaluation/daily_uef_pipeline.py`,
`tests/test_daily_uef_pipeline.py`, `tests/test_operator_ui.py`,
`docs/ground_rules/AGENT_RULES.md`, plus its own two new `docs/daily_patch/*.md`
files, `.vscode/`, `tmp/`) was left exactly as found -- not committed, not
reverted, not read-modified.
