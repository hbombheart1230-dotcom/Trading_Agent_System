# Q15 Candidate Filtering Patch - 2026-07-10

## Summary

Q15 applies exactly one behavior patch: tighter candidate filtering for runner-up cascade entries.

This patch does not change scanner scoring, strategist prompts, commander approval logic, monitor entry formulas, monitor exit formulas, or order execution. It only limits when a lower-ranked runner-up can replace the original top candidate.

## Background

Q13 identified `scanner_alignment_score` as the weakest repeated attribution axis.

Q14 decomposed that weakness into root causes. The strongest behavior candidates were:

- `Candidate Filtering`
- `Scanner Ranking Failure`

The 2026-07-10 review showed that many losing trades were not arbitrary strategist or commander symbol changes. They were cases where the top scanner candidate was not ready, then the system cascaded into a weaker runner-up candidate.

## Decision

Patch `Candidate Filtering` first.

Reason:

- It is narrower and lower risk than changing scanner scoring.
- It directly addresses runner-up cascade losses.
- It preserves the existing scanner, strategist, commander, and monitor architecture.
- It can be evaluated with the frozen Q13/Q14 reports after deployment.

## Known Limitation

This patch does not solve the full ranking problem.

Historical review already shows that scanner rank 1 trades are also not reliably profitable. Therefore Q15 should not be interpreted as "rank 1 is good and runner-ups are bad."

There are two separate problems:

1. `Scanner Ranking Failure`
   - Rank 1 itself may not have enough edge.
   - This is the deeper scanner scoring and selection-quality problem.

2. `Candidate Filtering`
   - When rank 1 is not ready, the system may cascade into an even weaker runner-up.
   - This is the narrower leakage problem patched by Q15.

Q15 only addresses the second problem.

If post-patch results still show poor rank 1 performance, the next behavior candidate should be `Scanner Ranking Failure`, not another runner-up filtering patch.

## Changed File

- `libs/runtime/monitor_candidate_cascade.py`

## New Runner-Up Gate

Before a runner-up candidate can be evaluated as a fallback entry, it must pass three checks.

### 1. Rank Cap

Default:

- `q15_max_runner_up_rank = 3`

Meaning:

- Even if commander expands candidate watch to rank 5, rank 7, or lower, Q15 restricts actual fallback candidates to rank 3 or better by default.

### 2. Score Gap Cap

Default:

- `q15_max_score_gap = 0.20`

Meaning:

- If the runner-up score is more than 0.20 below the top candidate score, it is excluded before monitor fallback evaluation.

### 3. Runner-Up Blocker Gate

If the runner-up already carries a high-risk expected blocker, it is excluded before cascade.

Examples:

- `below_vwap_reclaim_not_ready`
- `pullback_below_vwap_reclaim_not_ready`
- `volume_confirmation_missing`
- `cost_filter_failed`
- `cost_adjusted_edge_not_ready`
- `directional_edge_evidence_missing`
- `pullback_not_mature`
- `too_extended_from_vwap`
- `still_overextended_after_pullback`

### 2026-07-16 Narrow Adjustment

`volume_insufficient` was removed from this anticipated blocker list after the
post-Q15 shadow cohort showed positive net forward returns at +5m, +15m, and
+30m. This only allows the candidate to reach Monitor. Monitor's current-data
volume hard gate is unchanged.

Decision and evidence:

- `docs/q13_q14_validation/post_q15_close_decision_2026-07-16.md`

## What This Patch Does Not Mean

This patch does not mean "always buy scanner rank 1."

It means:

> If rank 1 is not ready, only allow a runner-up when the runner-up is still near the top, close in score, and independently free of obvious blockers.

## Expected Effect

Expected improvements:

- fewer weak runner-up entries
- lower `Candidate Filtering` root cause count
- better `scanner_alignment_score`
- less cascade into rank 5+ candidates

Not expected from this patch alone:

- rank 1 trade win rate becoming good by itself
- scanner score formula becoming profitable
- monitor entry timing becoming fixed
- exit horizon behavior becoming fixed

Risks to monitor:

- trade count may drop
- some valid runner-up opportunities may be skipped
- if scanner rank 1 is often not ready and runner-ups are filtered out, no-trade frequency may rise

## Validation After Patch

Keep Q13/Q14 frozen.

Track after deployment:

- Q13 `scanner_alignment_score`
- Q14 `Candidate Filtering` count and average return
- Q14 `Scanner Ranking Failure` count and average return
- scanner rank 1 trade win rate and average return
- trade count
- no-trade count
- Missing Evidence ratio
- daily average return and profit factor

Do not apply another behavior patch until this patch has enough post-change evidence.

## Tests

Updated tests:

- `tests/test_monitor_candidate_cascade.py`
- `tests/test_monitor_exit_guard.py`

Covered cases:

- commander-expanded runner-up range is capped by Q15
- large score-gap runner-up is skipped
- runner-up with expected blocker is skipped
- anticipated `volume_insufficient` reaches Monitor while the actual volume gate remains active
- existing rank 2 and rank 3 fallback behavior still works when candidates are clean
