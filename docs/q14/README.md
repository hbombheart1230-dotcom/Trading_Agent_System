# Q14 Scanner Alignment Root Cause

## Purpose

Q14 does not add new Q13 evaluation axes.

Q14 decomposes why `scanner_alignment_score` is repeatedly low. It is a root-cause analysis layer, not a trading behavior patch.

## Scope

Q14 classifies each realized trade into one scanner-alignment root cause:

- `Scanner Ranking Failure`
- `Rank Drift`
- `Strategist Override`
- `Candidate Filtering`
- `Symbol Mapping`
- `Missing Evidence`
- `Aligned / No Alignment Issue`

## Outputs

Daily output:

- `reports/evaluation/daily/YYYY-MM-DD/scanner_alignment_root_cause_report.json`
- `reports/evaluation/daily/YYYY-MM-DD/scanner_alignment_root_cause_report.md`

Range output:

- `reports/evaluation/range/YYYY-MM-DD_YYYY-MM-DD/scanner_alignment_root_cause_report.json`
- `reports/evaluation/range/YYYY-MM-DD_YYYY-MM-DD/scanner_alignment_root_cause_report.md`

## Metrics

Each root cause reports:

- trade count
- return observation count
- win rate
- average return
- profit factor
- maximum drawdown
- negative impact

The report separates:

- largest observed root cause
- largest behavior root cause

`Missing Evidence` can be the largest observed root cause, but it is not a behavior patch. If `Missing Evidence` dominates, fix observability first or use only the evidence-backed behavior root cause for Q15.

## Freeze Rules

Q14 is observation-only.

Do not change:

- scanner ranking
- strategist prompt
- commander approval
- monitor entry
- monitor exit
- order execution

## Q15 Gate

Q15 may select exactly one behavior patch.

The selected patch must reference the largest evidence-backed Q14 root cause. Multiple simultaneous behavior changes are not allowed.

## Q15 Patch Selected

After the 2026-07-10 close, Q15 selected `Candidate Filtering` as the first behavior patch.

This does not mean scanner ranking is cleared. It means the first patch is the narrower, lower-risk issue:

- top candidate not ready
- runner-up cascade allowed too broad a candidate set
- lower-ranked runner-up entered without enough independent quality

The patch is documented here:

- `docs/q13_q14_validation/q15_candidate_filtering_patch_2026-07-10.md`

Scanner ranking remains an observed root cause candidate, but it is not patched at the same time. Q13/Q14 must continue to measure it after the Q15 Candidate Filtering patch.

## Interpretation Boundary

Q15 Candidate Filtering should be read as a leakage-control patch, not as proof that scanner rank 1 is profitable.

Known interpretation:

- If losses fall because weak runner-up entries disappear, Q15 worked as intended.
- If trade count falls but rank 1 trades are still weak, the remaining issue is likely `Scanner Ranking Failure`.
- If both runner-up losses and rank 1 losses remain weak, the next patch should not add more filtering. It should decompose and adjust scanner ranking components.

Do not merge these two conclusions:

- `Candidate Filtering`: the system bought weaker fallback candidates too easily.
- `Scanner Ranking Failure`: the scanner's first choice itself lacks edge.
