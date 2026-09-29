# 2026-09-29 Daily UEF -- Canonical Publication Authority Closure

## Scope

A bounded re-audit (Codex) found one remaining publication-authority boundary after Fix2's H1
(single-capture), H2 (closeout bypass), H3 (freshness contracts), and M1 (atomicity) fixes. This closes it.
UEF-5 through UEF-9 remain frozen and untouched -- this is orchestration, publication authority, and a
formal completion/verification layer only, never a change to how any UEF stage decides anything.

## Findings closed

**Legacy CLI canonical bypass.** `scripts/run_alpha_research_board.py` still called
`write_alpha_research_board()` directly -- a second, independent canonical-write path with zero UEF-9
involvement, writing the dated Board and advancing `latest.json`/`.md` unconditionally. Fixed: that CLI now
only ever calls `build_alpha_research_board()` (read-only) and prints/optionally writes a diagnostic
snapshot to an explicitly non-canonical location; it refuses to run at all if `--output-dir` is pointed at
the canonical path. Verified by a repository-wide `git grep` (now a permanent regression test): the
generation/pointer writer functions are called from exactly one implementation file.

**Unknown-source permissiveness.** The freshness guard treated any source key with no registered contract
as automatically tolerated. Fixed: every one of the 11 source keys `build_alpha_research_board`'s
canonicalized output can ever populate is now explicitly registered (7 confirmed directly against
`libs/reporting/alpha_research_board/contracts.py::SOURCE_PATHS`, plus `btc_woori_hypothesis` and
`large_cap_daily` added by the builder itself, plus `strategist_stage2_effectiveness` and
`short_alpha_discriminator` added later inside `canonicalize_board` -- the latter two were easy to miss on
a first read and were only found by actually running the builder and inspecting its real output). A source
key with no registered contract now rejects the canonical run outright.

**No bundle-completion authority.** A directory containing `alpha_research_board.json` plus UEF-7/8/9
output directories was previously indistinguishable from a genuinely complete, verified daily result --
nothing bound them together or proved none had been tampered with or partially written. Fixed with a
generation/manifest/pointer model:

- Each successful daily run writes ONE generation at
  `reports/evaluation/alpha_research_board/<day>/generations/<authority_id>/` (`authority_id` = the UEF-9
  run_id -- deterministic, content-derived, never a timestamp), containing the exact captured Board plus a
  `COMPLETE.json` manifest binding it, by sha256 digest, to the exact UEF-7/8/9 output files already written
  to their own canonical paths. The manifest is written LAST, only after every other file exists.
- `verify_generation_manifest()` re-checks digests, run-ID bindings, and `authority_status=VALID` before
  anything is allowed to point at a generation -- including a self-check performed immediately after every
  write, before `current.json`/`latest.json` ever advance.
- `<day>/current.json` and the global `latest.json` are atomic pointers, only ever updated after a
  generation has passed verification. A failed or interrupted rerun for a day that already has a valid
  generation leaves that generation's pointer completely untouched -- the content-derived `authority_id`
  naming means a different/failed attempt can never collide with or overwrite the prior valid generation's
  own directory.
- `<day>/alpha_research_board.json`/`.md` remain as a legacy-compatibility VIEW (copied from the current
  generation after verification) for human/report navigation -- explicitly documented as non-authoritative.
- `latest.json` is the sole machine authority; `latest.md` is a presentation-only derived view. If
  regenerating `latest.md` fails, machine authority (`latest.json`) is completely unaffected --
  `write_latest_presentation()` swallows that failure by design and never raises it to the caller.
- `resolve_canonical_alpha_board()` is the one reader any future authoritative consumer should use --
  resolves the pointer, verifies the manifest, and only returns a Board if verification passes.

## Tests

`tests/test_daily_uef_pipeline.py`, 23 passed: the retained Fix2 coverage (updated for the generation model)
plus new coverage for every finding above -- legacy CLI cannot canonical-publish (including a subprocess
run against real diagnostic output), a repository-wide sole-writer check, unknown-source rejection, a
registered-optional-source-absent case, a partial bundle before `COMPLETE.json` leaving no authority, a
same-day replacement failure leaving the prior generation current, a complete generation's manifest/current/
latest/hashes all validating together, a tampered artifact failing verification, and a `latest.md` write
failure leaving `latest.json` completely valid. Broader regression (Alpha Board, UEF-7/8/9, closeout,
patch-notes, pytest-artifact-hygiene): 171 passed. `scripts/verify_uef_freeze_manifest.py`: 11/11 MATCH.

Two real bugs were found and fixed while building this: `DailyUefEvaluationResult(published=True, ...)` was
missing from the final success path (a copy-paste omission, caught immediately by the new tests), and
`_atomic_write_text()` needed `newline=""` -- without it, Windows text-mode writes silently translate `\n`
to `\r\n`, so a digest computed over the in-memory string no longer matched the bytes actually written to
disk, and every freshly-written generation failed its own immediate self-verification.

## 2026-09-29 re-check

Re-ran `scripts/run_daily_uef_evaluation.py --through-day 2026-09-29` against this repository's real
current state. Unchanged, correct result: **NOT_AVAILABLE** -- `prospective_candidates`, `fresh_change`,
`opening_cumulative`, `latent_reactivation` are still dated `2026-09-25`; no unknown-source findings (the
complete 11-key contract table now covers every real source). No generation written; `latest.json`/`.md`
untouched. Also re-ran the legacy CLI (`scripts/run_alpha_research_board.py --through-day 2026-09-29`)
directly against real data and confirmed `reports/evaluation/alpha_research_board/latest.json`'s own mtime
is unchanged afterward. **P1.2 Day-1 remains PARTIAL.**

## Status

- Scheduler: still NOT registered.
- P1.2 Day-1 = PARTIAL.
- UEF-5 through UEF-9 semantics: unchanged.
- P1.3 Docker work is unaffected and continues separately.
