# P1.2 Cross-Day Observation -- Day 1 (2026-09-29)

Observation only. No UEF-5..UEF-9 semantics touched by this document or by the investigation it records.

## Result

- P1.2 Day-1 = **PARTIAL**, reason = **AUTOMATION_NOT_WIRED**.
- UEF semantic status (wherever the chain actually ran) = **PASS**.
- Daily canonical Alpha Board + UEF pipeline = **GAP** (fixed same day -- see
  `docs/daily_patch/2026-09-29_daily_uef_eod_wiring.md`).

## What was found

No `reports/evaluation/alpha_research_board/2026-09-29/` (or `2026-09-28/`) directory existed on disk.
`latest.json`/`latest.md` still pointed at `through_day=2026-09-25`. The UEF-7/8/9 outputs that did exist
with today's date in their filenames (`UEF7RUN_5cc7cb2afd9cfd04`, `UEF8RUN_09af2f7cdb2977be`,
`UEF9RUN_34d8789cc40ea717`) were traced precisely: they are the artifacts of the earlier same-session P1.1
Real-Run Acceptance task (`tmp/p1_1_acceptance/run_chain.py` against the static
`REAL_RUN_CAPTURE_A.json`), not evidence of an automatic 2026-09-29 evaluation. Their numbers match the
stated P1.1 baseline exactly (candidate_count=14, pair_count=91, COMPARABLE=0, CONDITIONAL=7,
NOT_COMPARABLE=84, authority_status=VALID) because it is the same run being observed twice.

Wiring inspection confirmed why: the only Windows scheduled task
(`deploy/m28_launch_templates/windows/scheduler_task.xml`) invokes exclusively the live commander runtime
loop. Nothing invokes `scripts/run_alpha_research_board.py` or the UEF-7/8/9 CLIs automatically.
Classification: **AUTOMATION_NOT_WIRED**.

Everywhere the UEF chain itself actually ran (the P1.1 replay), every internal invariant held: candidate
universe conservation, pair conservation (91 = 14*13/2, 91 unique pair IDs), exact UEF-7/8/9 run-ID
bindings, `authority_status=VALID`, zero production/runtime state writes (verified directly against
`data/state/*` file mtimes). **UEF_REOPEN_REQUIRED = NO.**

## Fix and recovery attempt

See `docs/daily_patch/2026-09-29_daily_uef_eod_wiring.md` for the new
`libs/reporting/evaluation/daily_uef_pipeline.py` orchestrator, its tests, and the scheduler wiring
prepared (not yet registered). An independent audit subsequently found three real defects in that first
implementation (single-capture authority, a competing canonical publisher inside closeout maintenance, and
source-contract-unaware freshness with a publishable stale-bypass); see
`docs/daily_patch/2026-09-29_daily_uef_eod_wiring_fix2.md` for the correction. The conclusions below
reflect the corrected implementation.

Running that orchestrator against this repository's real current state for `through_day=2026-09-29`
correctly **FAILED (freshness_guard)**: `prospective_candidates`, `fresh_change`, `opening_cumulative`, and
`latent_reactivation` are all still dated `2026-09-25` in the underlying source files -- several upstream
cumulative shadow-evaluation pipelines have not advanced past that Friday, independent of the Alpha Board
persistence gap itself. This is the guard behaving correctly, not a defect: it refused to materialize a
board labeled `2026-09-29` that would have silently mixed in multi-day-stale content, exactly what the
guard exists to prevent. No 2026-09-29 board was written; `latest.json`/`.md` remain unchanged at
`2026-09-25`.

`2026-09-28` was investigated separately and classified `INSUFFICIENT_SOURCE_INPUT` (real trading-pipeline
activity that day per `reports/evaluation/daily/2026-09-28/daily_scorecard.json`, but
`broker_integrity=false` in that day's own Q9 readiness gate) -- not backfilled, since the missing evidence
cannot be faithfully reconstructed after the fact.

## Next

Days 2+ of P1.2 cross-day observation, and confirming the underlying cumulative shadow pipelines resume
advancing daily, are follow-on work -- not performed in this session. P1.3 Docker work is unaffected and
continues in parallel.
