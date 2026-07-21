# Q15 Candidate - Scanner Score Component Failure

Date: 2026-07-08

Scope: documentation only. No runtime behavior change.

## Purpose

Q13/Q14 validation is frozen. This document fixes the current Q15 behavior patch candidate using the available 2026-06-01 through 2026-07-08 evidence.

The current candidate is not "change the whole scanner." The candidate is narrower:

> Decompose scanner raw score components for aligned losing Top1 trades, then promote only one scoring defect into Q15 if validation confirms it.

## Evidence Window

Source artifacts:

- `reports/evaluation/range/2026-06-01_2026-07-08/scanner_score_component_dataset.json`
- `reports/evaluation/range/2026-06-01_2026-07-08/scanner_score_component_summary.json`
- `reports/evaluation/range/2026-06-01_2026-07-08/scanner_alignment_root_cause_report.json`

Coverage:

| Item | Count |
|---|---:|
| Total trades | 79 |
| Trades with return observation | 74 |
| Trades with scanner evidence | 78 |
| Trades with scanner detail payload | 73 |
| Trades with component scores | 73 |

Overall observed performance:

| Count | Wins | Losses | Win rate | Avg return | Profit factor |
|---:|---:|---:|---:|---:|---:|
| 74 | 6 | 66 | 8.11% | -1.1335% | 0.1446 |

## Current Root Cause Position

Observed behavior-level root cause:

| Root cause | Trades | Observed | Win rate | Avg return | Profit factor |
|---|---:|---:|---:|---:|---:|
| Scanner Ranking Failure | 14 | 14 | 0.0% | -1.7197% | 0.0 |
| Candidate Filtering | 7 | 6 | 0.0% | -1.5133% | 0.0 |
| Strategist Override | 3 | 3 | 0.0% | -1.2783% | 0.0 |

Interpretation:

- The strongest actionable candidate is `Scanner Ranking Failure`.
- This does not mean the scanner should be replaced.
- It means aligned Top1 losers need their score components audited before one behavior patch is selected.

## Component Findings

### 1. `below_vwap_reclaim_not_ready`

Expected monitor block:

| Signal | Observed | Win rate | Avg return | Profit factor |
|---|---:|---:|---:|---:|
| `below_vwap_reclaim_not_ready` | 21 | 0.0% | -1.6661% | 0.0 |

Dominant block:

| Signal | Observed | Win rate | Avg return | Profit factor |
|---|---:|---:|---:|---:|
| `below_vwap_reclaim_not_ready` | 12 | 8.3% | -1.6596% | 0.004 |

Interpretation:

- This is the strongest current defect candidate.
- It should not remain a weak soft penalty if validation confirms the pattern.
- Q15 candidate action: promote this from descriptive blocker to ranking-quality defect, not necessarily immediate hard veto.

### 2. `volume_confirmation_missing`

| Signal | Observed | Win rate | Avg return | Profit factor |
|---|---:|---:|---:|---:|
| `volume_confirmation_missing` | 4 | 0.0% | -2.1025% | 0.0 |

Interpretation:

- Sample is smaller than `below_vwap_reclaim_not_ready`.
- Loss severity is worse.
- Q15 should not patch this first unless the final validation days increase the sample or make it the dominant confirmed cause.

### 3. `relative_strength_score < 0.25`

| Bucket | Observed | Win rate | Avg return | Profit factor |
|---|---:|---:|---:|---:|
| `<0.25` | 6 | 0.0% | -1.0690% | 0.0 |

Interpretation:

- Weak relative strength is a credible defect.
- It is currently a secondary candidate because the sample is small.

### 4. `macro_chart_fit_score >= 0.75`

| Bucket | Observed | Win rate | Avg return | Profit factor |
|---|---:|---:|---:|---:|
| `>=0.75` | 20 | 5.0% | -1.6559% | 0.003 |
| `0.5-0.75` | 20 | 20.0% | -0.8165% | 0.460 |

Interpretation:

- High macro chart fit does not currently indicate better trade quality.
- This field should be treated as suspect for short-horizon trading.
- Q15 should not blindly invert or remove it. First action should be to stop treating it as strong positive evidence if it appears in the selected patch path.

### 5. `volume_surge` positive factor

| Positive factor | Observed | Win rate | Avg return | Profit factor |
|---|---:|---:|---:|---:|
| `volume_surge` | 9 | 0.0% | -1.0704% | 0.0 |

Interpretation:

- Current `volume_surge` behaves more like late-chase risk than confirmation.
- This is a strong candidate for reclassification, but it should be patched only if Q15 selects the volume-confirmation branch.

## Current Q15 Candidate Ranking

1. Promote `below_vwap_reclaim_not_ready` into a scanner ranking-quality defect.
2. Reclassify `volume_confirmation_missing` / `volume_surge` so weak or late volume cannot lift a candidate.
3. Add a relative-strength floor for scanner Top1 eligibility.
4. Reduce or neutralize high `macro_chart_fit_score` as a short-horizon positive signal.

Only one action may be selected for Q15.

## Non-Candidates For Immediate Q15

Do not patch these first based on current evidence:

- Strategist prompt tuning.
- Commander approval behavior.
- Monitor entry/exit timing.
- Full scanner rewrite.
- Multiple simultaneous scoring changes.

Reason:

- 2026-07-08 showed `Scanner Top1 = selected = executed`.
- The immediate defect is not selection authority drift.
- The current evidence points to scanner score interpretation, especially blocker-related candidates being ranked too high.

## Compressed Validation Decision

The original Q13/Q14 validation rule is 5 trading days.

For the current week, a compressed 4-day decision is allowed after Friday close only if all conditions below hold:

1. Q13/Q14 reports generate successfully for all 4 validation days.
2. Missing Evidence remains within threshold.
3. `Scanner Ranking Failure` is the largest behavior root cause on at least 3 of 4 days, or the cumulative behavior root cause impact is clearly dominated by `Scanner Ranking Failure`.
4. The selected Q15 candidate is supported by scanner component evidence, not by narrative interpretation alone.
5. No unresolved artifact integrity issue affects scanner score component fields.

If these conditions are not met, Friday's decision is `NO_GO`, and Q15 behavior patching remains blocked.

## Friday Close Decision Template

Use this structure after Friday close:

### Decision

GO / NO_GO

### Evidence

- Validation days:
- Report completeness:
- Missing Evidence:
- Largest behavior root cause by day:
- Cumulative behavior root cause:
- Scanner component defect:

### Candidate

One of:

- `below_vwap_reclaim_not_ready` ranking-quality defect
- `volume_confirmation_missing` / `volume_surge` reclassification
- `relative_strength_score` floor
- `macro_chart_fit_score` neutralization

### Rationale

Explain why this one candidate is selected and why other candidates are deferred.

### Q15 Constraint

Only one behavior patch is allowed.

