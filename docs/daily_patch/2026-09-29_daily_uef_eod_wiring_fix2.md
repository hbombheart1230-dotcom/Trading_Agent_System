# 2026-09-29 Daily UEF EOD Wiring -- Fix2 (Independent Audit Correction)

## Scope

An independent audit of the first daily-UEF-wiring implementation
([2026-09-29_daily_uef_eod_wiring.md](2026-09-29_daily_uef_eod_wiring.md)) found three HIGH-severity and
one MEDIUM-severity defect before scheduler registration. This closes all four. Frozen UEF-5 through UEF-9
semantics remain untouched -- this is orchestration, publication-authority, and atomicity hardening only.
No trading strategy or execution semantics touched.

## Findings and fixes

**H1 -- single-capture authority broken.** The first implementation called `build_alpha_research_board()`
once to feed UEF-7/8/9, then a second time inside `write_alpha_research_board()` to persist -- so the
Board UEF-9 actually verified was not provably the exact Board written to the canonical dated path if an
underlying source mutated between the two calls (this host runs a live, concurrently-writing trading
process as its normal condition). Fixed: `build_alpha_research_board()` is now called EXACTLY ONCE per
run. Two new functions, `persist_canonical_alpha_board()` and `advance_latest_pointer()`, write that exact
already-built object -- neither rebuilds anything. Regression: `test_persisted_board_matches_captured_
board_not_a_later_mutation` captures once, mutates a source file mid-run, and asserts both that the build
function was called exactly once and that the persisted file does not reflect the mutation.

**H2 -- competing canonical publisher.** `libs/reporting/closeout_maintenance.py`'s
`write_closeout_maintenance_report()` independently called `write_alpha_research_board()`, which persists
the canonical dated Board and unconditionally advances `latest.json`/`.md` -- with no UEF-9 involvement at
all. Fixed: that call now uses `build_alpha_research_board()` (read-only) and writes its result to an
explicitly non-canonical location, `reports/evaluation/closeout_alpha_board_snapshot/<day>/`, for
closeout's own reporting needs only. `libs/reporting/evaluation/daily_uef_pipeline.py` is now the ONLY code
path in this repository permitted to write `reports/evaluation/alpha_research_board/<day>/` or
`latest.json`/`.md`. Regression: `test_closeout_maintenance_cannot_advance_canonical_board_or_latest`.

**H3 -- freshness not source-contract-aware, and the stale bypass could publish.** The original guard
required every dated source to equal the target day uniformly, with no distinction between sources whose
contract is actually daily and sources that are not, and `--allow-stale-sources` could still reach
canonical publication. Fixed with two changes:

- An explicit per-source contract table (`_SOURCE_FRESHNESS_CONTRACTS`). Verified directly against real
  source content: `prospective_candidates`, `fresh_change`, `opening_cumulative`, and
  `latent_reactivation` are produced daily by closeout and must carry `through_day == target_day`
  (including a legitimate same-day zero-event state -- `VALID_NO_EPISODES` / `NO_OPENING_RANK1` / zero
  redetections is still a fresh, dated file; freshness is judged purely by the date stamp, never by
  row/event count). `feature_candidates`
  (`reports/evaluation/feature_mart/opening_rank1/candidate_selection.json`) was investigated directly: it
  carries no `through_day`/`day` field at all, and its own payload instead carries a FIXED, one-time
  `selection_period` (`validation_start`/`selection_end_day`, a backtest window, not a daily cadence) --
  `schema_version=rank1_candidate_selection.v1`, `behavior_effect=NONE_OFFLINE_RESEARCH_ONLY`. It is
  required to be present (it feeds the core candidate pool) but is never date-compared, because its own
  contract has no daily date to compare. No other source got a new rule; ungoverned sources keep the
  existing `PASS_WITH_MISSING_SOURCES` tolerance.
- The CLI's `--allow-stale-sources` flag was replaced with `--diagnostic`, which maps to
  `run_daily_uef_evaluation(canonical=False)`. In that mode the freshness contracts are not enforced, but
  the function's own persistence branch is structurally unreachable unless `canonical=True` -- there is no
  code path by which a diagnostic run's success can write any canonical file, regardless of outcome.
  Regression: `test_diagnostic_mode_never_writes_canonical_files_even_on_success`.

**M1 -- non-atomic publication.** File writes previously used a plain `path.write_text()`, which can leave
a half-written file on interruption. `persist_canonical_alpha_board()` and `advance_latest_pointer()` now
write to a temp file in the same directory, `fsync` it, then `os.replace()` it into place -- atomic on both
POSIX and NTFS for a same-volume rename. The dated bundle is always fully written before `latest.json`/
`.md` is touched. Regression: `test_publication_failure_leaves_previous_latest_unchanged` (simulates a
failure during the final publish step and confirms the prior day's `latest.json` is byte-identical
afterward) and `test_atomic_write_never_leaves_partial_file_on_failure`.

## Canonical authority invariant (now explicit)

Canonical daily Alpha Board publication = the Board captured by the daily EOD evaluator, AND UEF-7 valid,
AND UEF-8 valid, AND UEF-9 `authority_status == VALID`. Only then may
`reports/evaluation/alpha_research_board/<day>/`, `latest.json`, and `latest.md` advance. This is now
enforced structurally (single capture, sole publisher, canonical/diagnostic mode separation), not just by
convention.

## Regressions

`tests/test_daily_uef_pipeline.py` (15 tests, all passing), `tests/test_closeout_maintenance.py` (updated,
passing), `tests/test_alpha_research_board.py`, `tests/test_uef7_alpha_board_normalization.py`,
`tests/test_uef8_fair_comparison_validation.py`, `tests/test_uef9_formal_authority.py`,
`tests/test_patch_notes_sync.py`, `tests/apps/api/test_patch_notes.py` -- 157 passed total.
`scripts/verify_uef_freeze_manifest.py`: 11/11 MATCH, 0 mismatch -- no frozen UEF-1..UEF-3 file touched.

## 2026-09-29 re-check

Re-ran `scripts/run_daily_uef_evaluation.py --through-day 2026-09-29` against this repository's real
current state after Fix2. Same, correct result as before Fix2: **NOT_AVAILABLE** --
`prospective_candidates`, `fresh_change`, `opening_cumulative`, `latent_reactivation` are still dated
`2026-09-25`. `feature_candidates` is no longer (and was never validly) part of that finding under the
refined per-source contract. No board manufactured; `latest.json`/`.md` unchanged. P1.2 Day-1 remains
**PARTIAL** until a genuine current-day canonical chain succeeds.

## Status

- Scheduler: still NOT registered. The prepared 16:00 KST trigger remains provisional -- source readiness
  (the four required daily sources actually advancing) is the real gate, not the clock time.
- P1.2 Day-1 = PARTIAL (unchanged from before Fix2 -- this was a publication-safety correction, not a
  resolution of the upstream data gap).
- P1.3 Docker work is unaffected and continues separately.

## Correction (bounded re-audit, same day)

A further, deliberately bounded Codex re-audit of this Fix2 found the single-capture and closeout-bypass
fixes above genuinely correct, but identified real remaining gaps this document did not previously claim to
close: **a second, legacy canonical-write path** (`scripts/run_alpha_research_board.py` still called
`write_alpha_research_board()` directly), **unknown-source permissiveness** (any source key with no
registered contract was silently treated as optional), and, most importantly, **no real bundle-completion
authority** -- a directory containing `alpha_research_board.json` plus UEF-7/8/9 output directories was
already indistinguishable from a genuinely complete, verified daily result; nothing bound them together or
proved none of them had been tampered with or partially written. See
[Fix3 (Daily UEF Canonical Authority Closure)](2026-09-29_daily_uef_authority_closure.md) for the fix:
generation/manifest/pointer authority replacing plain file writes as the definition of "canonical".
