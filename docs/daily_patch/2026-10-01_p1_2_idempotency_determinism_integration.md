# 2026-10-01 -- P1.2 Idempotency/Determinism Integration onto the Canonical Host Branch

## Trigger

A "FINAL DAILY UEF IDEMPOTENCY AUTHORITY CHECK" task asked to verify the live
Windows Scheduled Task (`TradingAgent-DailyUefEvaluation`) actually runs code
containing the already-approved P1.2 same-day idempotency/determinism fix
(commits `6b59e5a` + `32beff6` on `codex/p1-2-idempotency-fix`, 2026-09-30;
final integrated SHA `025a16a4...` on `codex/p1-2-final-integration`).

## Live task inspection (read-only, before any change)

`Get-ScheduledTask -TaskName "TradingAgent-DailyUefEvaluation"`:
`Execute=C:\Trading_Agent_System\venv\Scripts\python.exe`,
`Arguments=scripts/run_daily_uef_evaluation.py`,
`WorkingDirectory=C:\Trading_Agent_System` -- the task's working directory is
this repository's own primary checkout, not a separate worktree.

In that exact directory: `git rev-parse HEAD` =
`ad9913e80ad72d8b597a00b8d235698a7cc2a75e`, branch =
`codex/observability-20260824`. `codex/p1-2-idempotency-fix` was never
merged into this branch -- `6b59e5a`/`32beff6` do not appear in
`git log --oneline -20` for this branch.

## Verified from code, not only ancestry

Per the task's own explicit instruction, absence was confirmed two ways, not
just by commit history:

- `git show HEAD:libs/reporting/evaluation/daily_uef_pipeline.py | grep -i "already_complete\|idempoten\|CANONICAL_SOURCE_CONFLICT\|MULTIPLE_COMPLETE"` -- no matches.
- The same grep against the actual **on-disk working-tree file** (what the
  live task's own Python process actually imports and executes, since
  Task Scheduler runs from a plain working directory, not a clean git
  checkout) -- also no matches. The working tree already carried unrelated,
  uncommitted "P1.2 Daily UEF Automation Integration" work (an observation
  registry, `record_daily_observation()`) from a separate, concurrent task --
  that addition records metadata about a day's generation but contains no
  preflight gate before UEF-7/8/9 publication runs.
- `libs/reporting/alpha_research_board/builder.py` (the determinism half of
  the approved fix) was untouched in both committed HEAD and the working
  tree -- still using hash-seed-dependent `Counter.most_common(1)` for tie
  resolution.

**Conclusion: P1_2_IDEMPOTENCY_PRESENT=NO, P1_2_DETERMINISM_PRESENT=NO.**
This was the blocker the task anticipated.

## Read-only 2026-10-01 state (before any change)

Exactly one generation directory (`UEF9RUN_e1c4ae6eab1ecaad`) under
`reports/evaluation/alpha_research_board/2026-10-01/generations/`;
`current.json` and `latest.json` both point to it; the P1.2 observation
registry has exactly one `2026-10-01` entry with the matching
`authority_id`. No preflight was invoked at this stage -- none existed yet
to invoke, and the task's own instruction was explicit: if no safe,
non-writing path is available, stop rather than run the real task.

## Integration

Applied `6b59e5a`'s actual diff content (not a raw cherry-pick, since the
target file has diverged under the other party's uncommitted work) onto the
current on-disk state:

- `libs/reporting/evaluation/daily_uef_pipeline.py`: added
  `_verified_complete_generations()` (read-only; glob verified `COMPLETE.json`
  manifests for the target day, pair each with its Board's semantic digest)
  and a preflight block inserted between the freshness-contract check and
  the UEF-7 call, inside the existing `if canonical:` guard -- so diagnostic
  (`canonical=False`) runs are unaffected, matching the approved design
  exactly. 0 verified COMPLETE -> proceeds normally; exactly 1 with matching
  identity -> `idempotency_status="ALREADY_COMPLETE"`, `published=False`,
  zero UEF-7/8/9/pointer/registry writes; exactly 1 with a different
  identity -> `"CANONICAL_SOURCE_CONFLICT"`, fail closed; 2+ ->
  `"MULTIPLE_COMPLETE_CONFLICT"`, fail closed. Added `idempotency_status`
  to `DailyUefEvaluationResult` and its `to_dict()`.
- `libs/reporting/alpha_research_board/builder.py`: added `_largest_key()`
  (count descending, key ascending) replacing `Counter.most_common(1)` for
  `_prospective_concentrations()`'s `largest_day`/`largest_symbol` --
  without this, two runs over identical underlying data could still produce
  different Board semantic digests purely from Python's hash-seed-dependent
  set iteration order, which would make the preflight's own identity
  comparison unreliable.

**One compatibility adaptation beyond the original commit**, required
because the approved fix predates the other party's observation-registry
addition and the two were never integrated together before now: the
`ALREADY_COMPLETE` return now also reports `observation_registry_path`
(the same deterministic path `record_daily_observation()` always writes to)
even though it does not call that function again on a short-circuited run --
this keeps the registry itself byte-for-byte unchanged on a no-op (as the
approved fix's own test requires) while still giving every caller, old or
new, a non-`None` path back. Verified this keeps the other party's own
pre-existing `test_completed_day_creates_one_derived_p1_2_observation_record`
passing unmodified.

## Tests

Ported the approved commit's full test suite onto the current (diverged)
`tests/test_daily_uef_pipeline.py`, adapted only where the file had already
moved on without it:

- `test_prospective_concentration_ties_use_canonical_key_order`,
  `test_prospective_concentration_is_stable_across_python_hash_seeds` (new).
- `test_rerun_against_unchanged_input_is_idempotent` updated to assert
  `second.published is False` / `second.idempotency_status == "ALREADY_COMPLETE"`
  instead of the old (now-incorrect under the fix) `first.to_dict() == second.to_dict()`.
- `test_same_complete_preflight_keeps_pointers_and_registry_unchanged`,
  `test_different_complete_preflight_fails_closed_before_uef_writes`,
  `test_multiple_complete_preflight_fails_closed_without_writes` (new) --
  adapted to read the real registry path off the first result
  (`first.observation_registry_path`) rather than hand-writing a fixture
  registry, since the registry mechanism is now genuinely present.
- `test_same_day_replacement_failure_leaves_prior_generation_current`
  renamed to `test_same_day_source_conflict_leaves_prior_generation_current`
  and rewritten per the approved diff: asserts a fail-closed
  `CANONICAL_SOURCE_CONFLICT` from the preflight itself, rather than the old
  test's injected `advance_current_pointer` crash (a failure mode the new
  preflight makes structurally unreachable for this scenario, since the
  conflict is now caught before any UEF/pointer write is attempted at all).

`python -m pytest tests/test_daily_uef_pipeline.py -q`: **29/29 pass.**
Broader sweep (`test_q9_day_validity.py`, `test_q9_evaluation.py`,
`test_closeout_maintenance.py`, `test_closeout_durable_completion_authority.py`,
`test_closeout_single_owner_guard.py`): **65/65 pass.**
`scripts/verify_uef_freeze_manifest.py`: **11/11 MATCH** (unaffected --
`daily_uef_pipeline.py` and `builder.py` are the publication orchestrator and
the Board builder, not among the frozen UEF-1/2A/2B/3A/3B/3C core files).

## Live safe-preflight attempt against real 2026-10-01 data

With the fix integrated, `run_daily_uef_evaluation(canonical=True)` against
the real repo for `through_day="2026-10-01"` would, by design, hit the new
preflight and return `ALREADY_COMPLETE` with zero further writes (confirmed
exhaustively via the synthetic `tmp_path` tests above). Attempting to invoke
this directly against the real repository was **blocked by this session's
own safety classifier** ("Modify Shared Resources") before it could run --
per the task's own explicit fallback instruction, this was not worked around
through any other method. `sha256sum` of `current.json`, `latest.json`, and
the observation registry were taken before the attempt and reconfirmed
identical after -- zero mutation occurred, because nothing executed.

**Required fields:**

```
NEW_GENERATION_CREATED = NO
CURRENT_MUTATED = NO
LATEST_MUTATED = NO
REGISTRY_MUTATED = NO
```

## Preserved, unmodified by this change

HOST runtime decision, the closeout durable-completion-authority fix, the
Daily UEF entrypoint START/END logging, the Scheduled Task's S4U logon type
and disabled battery restrictions, and all prior patch-note history. UEF-7/8/9
core semantics (the frozen 11-file manifest), Step5C, Step5D, and trading/
strategy semantics were not touched.
