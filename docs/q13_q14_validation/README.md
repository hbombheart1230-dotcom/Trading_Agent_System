# Q13/Q14 Validation and Q15 Patch

## Status

Q13 and Q14 are frozen.

Q15 behavior patching has started after the 2026-07-10 close.

Current Q15 patch:

- `Candidate Filtering`
- Patch note: `docs/q13_q14_validation/q15_candidate_filtering_patch_2026-07-10.md`

Q13/Q14 remain the evaluation baseline for checking whether Q15 improves the system.

Current operating phase:

- `Q16 closed: RETAIN`
- `Q17 directional-edge contract: CONTRACT_REPAIRED`
- `same_symbol_loss_reentry_control: APPLIED_2026_07_29`
- Close review: `docs/q13_q14_validation/q8_q17_close_review_2026-07-29.md`
- Reentry patch: `docs/q13_q14_validation/same_symbol_loss_reentry_control_2026-07-29.md`
- The initial post-Q15 window closed on 2026-07-16 as `ADJUST_AND_RETEST`.
- The fixed two-day retest closed on 2026-07-21 without extension.
- Retain removal of the anticipated `volume_insufficient` pre-veto.
- Monitor's actual volume hard gate remains active.
- No broader runner-up or volume relaxation is authorized.
- Q16 applies one cost-horizon fit patch after the Q15 close: triggered signals
  no longer use ATR/volatility proxy alone as directional cost-edge evidence.
- Q17 supplies horizon-matched empirical expectancy when the historical
  evidence contract is satisfied. It does not re-enable proxy evidence.
- After a full same-day loss exit, only that symbol is blocked from reentry
  for the remainder of the Korean trading day.

Close decision:

- `docs/q13_q14_validation/post_q15_close_decision_2026-07-16.md`
- `docs/q13_q14_validation/post_q15_adjustment_retest_close_2026-07-21.md`
- `docs/q13_q14_validation/q16_cost_horizon_fit_patch_2026-07-21.md`
- `docs/q13_q14_validation/q16_day1_review_2026-07-23.md`
- `docs/q13_q14_validation/q16_close_decision_2026-07-24.md`
- `docs/q13_q14_validation/q17_directional_edge_contract_patch_2026-07-24.md`
- `docs/q13_q14_validation/same_symbol_loss_reentry_control_2026-07-29.md`

Artifact integrity fixes:

- `docs/q13_q14_validation/broker_stale_fill_reconciliation_fix_2026-07-22.md`
- `docs/q13_q14_validation/measurement_integrity_fix_2026-07-22.md`

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

## Cumulative Q8-Q17 Review Contract

The cumulative review is an additive evaluation layer. It does not change the
frozen Q13/Q14 formulas or any trading behavior.

Command:

```powershell
venv\Scripts\python.exe scripts\run_cumulative_improvement_review.py --start 2026-06-01 --end YYYY-MM-DD
```

Outputs:

- `reports/evaluation/range/<start>_<end>/cumulative_improvement_review.json`
- `reports/evaluation/range/<start>_<end>/cumulative_improvement_review.md`

The review adds four observations:

- Scanner candidate windows compressed into independent 15-minute episodes.
- First entry versus repeated same-day/same-symbol entries.
- Confirmed post-reclaim pullback shadow outcomes with live and mock costs kept separate.
- Strategist B versus Scanner A paired outcomes.

Scanner score components are preserved in new Q9 snapshots. Historical rows
that did not store these components remain missing; they are not reconstructed
or guessed.

## Q14 Causal Interpretation

Measurement authority update (2026-08-21):

- `docs/daily_patch/2026-08-21_q14_q18_measurement_integrity.md`
- A legacy Q13/Q14 validation `GO` is diagnostic-stability evidence only.
- It does not authorize a behavior patch.
- Q15 candidate generation uses `largest_structural_root_cause`, not the
  outcome-conditioned `largest_behavior_root_cause`.

The legacy Q14 label `Scanner Ranking Failure` is outcome-conditioned: it is
assigned when Scanner Top-1 alignment is present and the realized return is
negative. `Aligned / No Alignment Issue` is the positive counterpart.

Therefore:

- both labels remain unchanged for backward compatibility
- both are marked `outcome_conditioned`
- neither label alone can authorize a Scanner behavior patch
- structural causes such as `Candidate Filtering`, `Strategist Override`,
  `Symbol Mapping`, and evidence gaps are reported separately

The cumulative report exposes both:

- `largest_behavior_root_cause`: legacy frozen result
- `largest_structural_root_cause`: outcome-independent structural diagnostic

## Q17 Boundary

While Q17 fixed validation is active:

- cumulative reports may be regenerated
- artifact, schema, and report defects may be fixed
- raw score component coverage may improve for new observations
- no candidate in the cumulative report is automatically promoted
- entry, exit, Scanner, Strategist, Commander, and execution behavior remain frozen

After Q17 closes, exactly one behavior candidate may be selected. All other
candidates remain observational controls.

## Evaluation Integrity Close

The 2026-07-30 integrity cleanup, regenerated evidence counts, and permanent
test/runtime path-isolation contract are recorded in:

- `evaluation_integrity_close_2026-07-30.md`

This close is observability-only. It does not reopen frozen Q13/Q14 formulas or
authorize a trading behavior change.

## Canonical Q8-Q17 Final Review

The authoritative post-cleanup conclusion and latest 2026-06-01 through
2026-07-30 metrics are recorded in:

- `q8_q17_canonical_final_review_2026-07-30.md`

When an older Q8-Q17 review contains a conflicting numerical snapshot, use the
canonical final review. Older documents remain historical decision records and
must not override the post-cleanup aggregate.

## Q18 Bounded Promotion Review

Q18 is defined as a single-candidate promotion review, not a new evaluation
axis:

- `q18_post_reclaim_promotion_review_plan_2026-07-30.md`

It starts with immediate historical episode reaggregation. If evidence remains
insufficient, it observes at most five additional full trading days and then
closes without extension.

Q18 closed immediately as `RETAIN SHADOW`:

- `q18_close_decision_2026-07-30.md`
- `q18_validation_audit_2026-07-30.md`

The optional five-day extension was not started. No Q19 evaluation phase is
authorized by the result.

The 2026-08-21 integrity review does not reopen Q18. Historical aggregates that
do not contain horizon-specific `+30m` counts are retained as legacy records but
cannot be reused as promotion evidence.
