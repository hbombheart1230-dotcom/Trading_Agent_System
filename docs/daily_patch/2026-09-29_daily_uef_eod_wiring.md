# 2026-09-29 Daily UEF EOD Wiring (P1.2 Operational Prerequisite)

## Scope

Closes an operational gap found during P1.2 Day-1 observation (2026-09-29): the Alpha Board -> UEF-7 ->
UEF-8 -> UEF-9 evaluation chain had no automatic daily trigger and no single orchestration entry point, so
`latest.json`/`latest.md` had silently stalled at `through_day=2026-09-25` for at least two subsequent
weekdays. Frozen UEF-5 through UEF-9 semantics are unchanged -- this is orchestration/scheduling wiring
and a fail-closed freshness guard only, never a change to how any UEF stage decides anything. UEF-1..UEF-6
and Alpha Research Board v2's own construction logic are untouched. No trading strategy/runtime semantics
touched; no broker/execution code touched.

## Root cause

- `scripts/run_uef7_alpha_board_normalization.py` and `run_uef8_fair_comparison_validation.py` each
  independently rebuild the Alpha Board from scratch via `build_alpha_research_board()` -- they do not
  chain off each other's actual output.
- `scripts/run_uef9_formal_authority.py` requires the caller to pass already-written UEF-7/UEF-8 file
  paths by hand -- there was no automatic hand-off.
- `write_alpha_research_board()` (which produces the dated board files and `latest.json`/`.md`) advances
  `latest.json`/`.md` unconditionally the instant it is called, with no gate on whether the board -- or any
  downstream UEF stage -- is actually valid or fresh.
- The only existing Windows scheduled task
  (`deploy/m28_launch_templates/windows/scheduler_task.xml`) invokes exclusively the live commander runtime
  loop (`scripts/run_commander_runtime_once.py --live`). Nothing in this repository's scheduling ever
  invoked the Alpha Board builder or the UEF-7/8/9 CLIs.
- A second, more subtle finding: `build_alpha_research_board()`'s returned `through_day` field is always
  an ECHO of whatever the caller requested -- it is never derived from or validated against the underlying
  source data's own dates. Confirmed directly against this repository's own state:
  `tmp/p1_1_acceptance/REAL_RUN_CAPTURE_A.json` claims `through_day="2026-09-29"` at its top level while
  several of its own per-source entries (`fresh_change`, `latent_reactivation`, `opening_cumulative`,
  `prospective_candidates`) carry `through_day="2026-09-25"` -- so a naive `board.through_day == target_day`
  guard would always pass trivially, by construction, even against multi-day-stale content.

## Fix

- New module `libs/reporting/evaluation/daily_uef_pipeline.py`: the one scheduler-agnostic orchestration
  entry point. Sequences the existing, unmodified library functions (never reimplements Alpha Board or
  UEF-7/8/9 semantics): builds the board once in-memory, runs a fail-closed freshness guard, feeds that
  EXACT board object through UEF-7 -> UEF-8 -> UEF-9 (not three independent recomputations), and only
  persists anything -- including advancing `latest.json`/`.md` -- once UEF-9 has actually returned
  `authority_status=VALID`. Any failure at any stage leaves every existing file untouched.
- The freshness guard (`check_board_source_freshness`) checks each individual dated source's own
  `through_day` field (populated independently by the existing loader, from that source file's own
  payload) against the requested day, plus that two required, always-expected-daily sources
  (`feature_candidates`, `prospective_candidates`) are actually present -- not the vacuous top-level
  `board.through_day` echo.
- New CLI `scripts/run_daily_uef_evaluation.py --through-day YYYY-MM-DD` (defaults to today); exit code 0
  only on a full, valid chain.
- New scheduler wiring artifacts (not yet registered on this host -- registration changes live host
  automation and is left as a deliberate, separate manual step, mirroring how the existing commander
  scheduler task was originally registered):
  `deploy/m28_launch_templates/windows/daily_uef_evaluation_task.xml` (daily 16:00 KST trigger, minimal
  logic -- invokes only the new CLI, no Alpha Board/UEF logic in the XML itself) and
  `deploy/m28_registration_helpers/windows/register_daily_uef_evaluation_task.ps1`.
- Regression coverage in `tests/test_daily_uef_pipeline.py`: missing required sources fail closed; a
  source dated for a different day than requested is rejected even though the board's own top-level field
  would have passed; a fully successful run persists the dated board, advances `latest.json`/`.md`, and
  chains exact UEF-7/8/9 run-ID bindings; a simulated UEF-9 failure leaves `latest.json`/`.md` and the
  dated board directory untouched; three consecutive runs against unchanged input are byte-identical and
  reuse the same content-derived run IDs (idempotent); the module imports nothing from
  `libs.execution`/`libs.runtime`/Kiwoom transport code, and a run never writes anything under `data/`.

## 2026-09-29 recovery attempt

Ran `scripts/run_daily_uef_evaluation.py --through-day 2026-09-29` against this repository's actual current
state (not the `tmp/p1_1_acceptance/` capture). Result: **FAILED (freshness_guard)** -- `prospective_candidates`,
`fresh_change`, `opening_cumulative`, and `latent_reactivation` are all still dated `through_day=2026-09-25`.
This is the new guard working correctly, not a defect: several of the underlying cumulative shadow-evaluation
pipelines that feed the Alpha Board genuinely have not advanced past that Friday, so today's board cannot be
honestly materialized yet. No board was written; `latest.json`/`.md` remain at `2026-09-25`, exactly as
before this change. **2026-09-29 canonical recovery = FAILED, and left FAILED rather than forced through.**

## 2026-09-28 classification

`reports/evaluation/daily/2026-09-28/daily_scorecard.json` shows `decision_class=INSUFFICIENT_EVIDENCE`,
with the commander/strategist/scanner/monitor snapshot checks all present but `broker_integrity=false` --
the day had real trading-pipeline activity, but a piece of evidence this repository's own Q9 readiness gate
requires was not captured. Classified **INSUFFICIENT_SOURCE_INPUT** (not `EXPECTED_NO_BOARD` -- there is no
evidence 2026-09-28 was a non-trading day -- and not `MISSING_DAILY_RUN` -- the day clearly ran). No board
was backfilled for 2026-09-28: the missing evidence cannot be faithfully reconstructed after the fact.

## Status

- UEF-5 through UEF-9 semantics: unchanged.
- Daily canonical Alpha Board + UEF pipeline: implemented, tested, not yet producing a fresh
  `2026-09-29` board (upstream source data is still stale; see above).
- Scheduler wiring: prepared, not yet registered on the live host.
- P1.3 Docker work is unaffected and continues separately.

Detail: [P1.2 Day-1 observation](../research/uef_p1_2_day1_observation.md).

## Correction (Fix2, same day, after independent audit)

This first implementation had three real defects, found by an independent audit and corrected in
[Fix2](2026-09-29_daily_uef_eod_wiring_fix2.md). Recorded here rather than silently edited away:

- **This document's "Any failure at any stage leaves every existing file untouched" claim above was
  incomplete.** It was true of this orchestrator's own failure paths, but it did not account for a
  *second, independent* code path -- `libs/reporting/closeout_maintenance.py` -- that separately called
  `write_alpha_research_board()` directly, bypassing UEF-9 entirely and advancing the canonical dated Board
  and `latest.json`/`.md` on its own. Fix2 removed that call.
- The freshness guard rebuilt the Alpha Board a second time inside `write_alpha_research_board()` at
  publish time, so the exact object UEF-9 verified was not provably the exact object persisted if an
  underlying source mutated between the two builds (a live, concurrently-writing host is this repository's
  normal condition, not an edge case). Fix2 made the board a single in-memory capture, persisted directly.
- The freshness guard treated every dated source uniformly; it had no explicit contract distinguishing a
  source that is genuinely supposed to update daily from one that is not. Fix2 replaced it with an explicit,
  evidence-based per-source contract table, and separated "diagnostic inspection" from "canonical
  publication" so a stale-source bypass can never reach `latest.json`/`.md`.

See Fix2's own document for full detail and the corrected invariant statement.
