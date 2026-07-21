# Q13/Q14 Validation and Q15 Patch

## Status

Q13 and Q14 are frozen.

Q15 behavior patching has started after the 2026-07-10 close.

Current Q15 patch:

- `Candidate Filtering`
- Patch note: `docs/q13_q14_validation/q15_candidate_filtering_patch_2026-07-10.md`

Q13/Q14 remain the evaluation baseline for checking whether Q15 improves the system.

Current operating phase:

- `Post-Q15 two-day adjustment retest`
- The initial post-Q15 window closed on 2026-07-16 as `ADJUST_AND_RETEST`.
- Q15 remains active.
- Only the anticipated `volume_insufficient` pre-veto was removed; Monitor's
  actual volume hard gate remains active.
- No additional behavior patch is allowed during the two-day retest.

Close decision:

- `docs/q13_q14_validation/post_q15_close_decision_2026-07-16.md`

Post-Q15 decision tree:

- `docs/q13_q14_validation/post_q15_two_day_decision_tree_2026-07-14.md`

## Duration

The frozen Q13/Q14 validation default remains 5 actual trading days.

The current Q15 adjustment has a separate, fixed two-full-trading-day retest.
Do not extend it silently. Close it as `RETAIN`, `ROLL_BACK`, or
`INSUFFICIENT_EVIDENCE` using the contract in the 2026-07-16 close decision.

### Compressed 4-Day Exception

The default validation window remains 5 trading days.

For the week ending 2026-07-10, a compressed 4-day decision is allowed after Friday close only if:

- Q13/Q14 reports generate successfully for all 4 validation days.
- Missing Evidence remains within the configured threshold.
- `Scanner Ranking Failure` is the largest behavior root cause on at least 3 of 4 days, or cumulative behavior impact is clearly dominated by `Scanner Ranking Failure`.
- The Q15 candidate is supported by scanner score component evidence.
- No unresolved artifact integrity issue affects scanner score component fields.

If these conditions are not met, the Friday result is `NO_GO` and Q15 behavior patching remains blocked.

## Purpose

The purpose of Q13/Q14 validation is not to evaluate win rate directly.

The purpose is to verify that the frozen Q13/Q14 system produces stable, repeatable root-cause conclusions.

The purpose of Q15 is different:

- apply one behavior patch based on Q13/Q14 evidence
- keep the patch narrow
- compare post-patch results against the same frozen Q13/Q14 metrics

## Allowed During Validation

- instrumentation bug fixes
- report generation fixes
- schema fixes
- Missing Evidence calculation fixes
- artifact missing-file fixes

## Forbidden During Validation

- scanner logic changes
- strategist changes
- entry changes
- exit changes
- ranking changes
- new evaluation axes
- Q13/Q14 score formula changes

## Daily Checks

Q13:

- `selection_integrity_score`
- `scanner_alignment_score`
- `entry_timing_score`
- `exit_horizon_score`
- `evidence_quality_score`

Q14:

- `Scanner Ranking Failure`
- `Candidate Filtering`
- `Strategist Override`
- `Missing Evidence`

Additional validation row:

- `Exit Horizon`

## GO / NO-GO Rules

GO:

- `Scanner Ranking Failure` is the largest behavior root cause on at least 4 of 5 trading days.
- `Missing Evidence` remains below the configured threshold.
- Q13/Q14 reports are generated successfully.
- No instrumentation errors repeat.

NO-GO:

- `Missing Evidence` is too high.
- Root cause changes materially day to day.
- Q13/Q14 reports are incomplete.
- Instrumentation errors repeat.

## Missing Evidence Threshold

Validation uses fixed thresholds:

- total Missing Evidence ratio must be `<= 20%`
- each daily Missing Evidence ratio must be `<= 40%`

These thresholds are validation gates, not trading behavior rules.

## Command

Use an explicit 5-day list after each trading day is complete:

```powershell
venv\Scripts\python.exe scripts\run_q13_q14_validation.py --validation-id q13_q14_validation_YYYYMMDD --days YYYY-MM-DD YYYY-MM-DD YYYY-MM-DD YYYY-MM-DD YYYY-MM-DD
```

Or use a date range when the report folder contains only the target validation days:

```powershell
venv\Scripts\python.exe scripts\run_q13_q14_validation.py --validation-id q13_q14_validation_YYYYMMDD --start YYYY-MM-DD --end YYYY-MM-DD
```

## Q15 Gate

If validation is `GO`, Q15 may perform exactly one behavior patch.

Priority order:

1. `Scanner Ranking Failure`
2. `Candidate Filtering`
3. `Strategist Override`
4. `Exit Horizon`

If validation is `NO_GO`, behavior patching is prohibited and instrumentation must be fixed first.

For the current post-Q15 phase, this gate means:

- do not apply another behavior patch while Q15 is being evaluated
- do not loosen Monitor or scanner rules only because trade count is low
- first classify the result using the post-Q15 decision tree

## Applied Q15 Patch

Applied after 2026-07-10 close:

- `docs/q13_q14_validation/q15_candidate_filtering_patch_2026-07-10.md`

Patch target:

- `Candidate Filtering`

Why this target:

- Q13 repeatedly showed weak `scanner_alignment_score`.
- Q14 showed runner-up cascade filtering as a repeat behavior issue.
- This is narrower than changing scanner ranking.
- It does not alter strategist, commander, entry, exit, or execution logic.

Important limitation:

- Q15 does not prove that scanner rank 1 is profitable.
- Prior review already showed weak rank 1 outcomes.
- Q15 only blocks leakage from an unready top candidate into weaker runner-ups.
- If rank 1 remains poor after Q15, the next behavior candidate is `Scanner Ranking Failure`.

Post-patch validation must track:

- Q13 `scanner_alignment_score`
- Q14 `Candidate Filtering`
- Q14 `Scanner Ranking Failure`
- scanner rank 1 win rate and average return
- trade count
- no-trade count
- Missing Evidence
- daily average return and profit factor

Prior Q15 candidate documentation:

- `docs/q13_q14_validation/q15_scanner_score_component_candidate_2026-07-08.md`
