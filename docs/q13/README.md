# Q13 Attribution Evaluation

## Purpose

Q13 is the diagnostic layer after Q9. Its purpose is not to improve trading behavior directly, but to identify which part of the pipeline is most likely damaging results.

Q13 uses existing artifacts and reports to score these axes:

- `selection_integrity_score`
- `scanner_alignment_score`
- `entry_timing_score`
- `exit_horizon_score`
- `evidence_quality_score`

Scores are 0-100 only when evidence exists. Missing evidence must be reported as `INSUFFICIENT_EVIDENCE`, not treated as a bad score.

## Current Status

Q13 has been generated for:

- Freeze window: `2026-06-29` to `2026-07-06`
- Historical range: `2026-06-01` to `2026-07-06`

Generated reports:

- `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/attribution_score_window.md`
- `reports/evaluation/range/2026-06-01_2026-06-30/attribution_score_range.md`
- `reports/evaluation/range/2026-06-01_2026-07-06/attribution_score_range.md`

## Current Read

The broad historical range points to this order of concern:

1. `scanner_alignment_score`
2. `exit_horizon_score`
3. `entry_timing_score`

Entry timing remains important, but older June artifacts do not contain enough Q13 timing evidence to score it fairly. It must continue to be collected from Q13-ready live data.

## Q13 Freeze Rule

Q13 is now frozen as an attribution layer.

Freeze principles:

- do not add evaluation axes
- do not change score formulas
- keep report structure changes minimal
- allow only bug fixes and evidence reinforcement
- do not change trading behavior

The scoring axes remain:

- `selection_integrity_score`
- `scanner_alignment_score`
- `entry_timing_score`
- `exit_horizon_score`
- `evidence_quality_score`

The `INSUFFICIENT_EVIDENCE` policy remains unchanged.

Behavior changes are not allowed inside Q13:

- no scanner ranking changes
- no strategist prompt changes
- no commander approval changes
- no entry rule changes
- no exit rule changes
- no order/execution changes

## Required Reinforcement

Q13 needs reinforcement in evidence clarity, not in trading behavior.

Required reporting reinforcements:

1. Separate historical conclusions from live-Q13 conclusions.
   - June historical data is usable for scanner alignment and exit horizon.
   - June historical data is not sufficient for entry timing.

2. Show whether each axis is scored or evidence-limited.
   - `INSUFFICIENT_EVIDENCE` must be visible in summary tables.

3. Keep daily and range reports together.
   - Daily reports explain what happened that day.
   - Range reports decide which axis is repeatedly weak.

4. Do not treat an attribution axis as a behavior patch by itself.
   - `scanner_alignment_score` is an attribution axis.
   - The actual behavior patch target must be selected after Q14 root-cause decomposition.

## Decision Gate

Q13 can move to a behavior patch only when one axis is both:

- repeatedly weak across a meaningful range, and
- supported by evidence rather than missing fields.

Based on the 2026-06-01 to 2026-07-06 replay, the most repeatedly observed weakness is `scanner_alignment_score`.

However, `scanner_alignment_score` is an attribution axis, not the behavior patch itself. The actual Q15 behavior patch target must be selected after Q14 decomposes its root cause.
