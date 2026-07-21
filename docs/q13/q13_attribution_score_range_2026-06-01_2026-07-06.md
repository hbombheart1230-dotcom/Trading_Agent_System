# Q13 Attribution Score Range Review - 2026-06-01 to 2026-07-06

## Purpose

Reprocess earlier June data with the same Q13 attribution scoring framework so the conclusion is not based only on the 2026-06-29 freeze window.

This is observation-only. It does not change scanner, strategist, commander, monitor, entry, exit, or execution behavior.

## Generated Reports

- June only: `reports/evaluation/range/2026-06-01_2026-06-30/attribution_score_range.md`
- June through July 6: `reports/evaluation/range/2026-06-01_2026-07-06/attribution_score_range.md`

## Coverage

| Range | Active Days | Available Attribution Days | Scored Days | Total Trades | Scored Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-06-01 to 2026-06-30 | 22 | 22 | 18 | 61 | 61 |
| 2026-06-01 to 2026-07-06 | 26 | 26 | 21 | 74 | 74 |

All active days in the range were regenerated successfully.

## Axis Results

### 2026-06-01 to 2026-06-30

| Axis | Average Score | Scored Days | Interpretation |
| --- | ---: | ---: | --- |
| selection_integrity_score | 94.28 | 18 | Mostly intact; not the primary failure axis. |
| scanner_alignment_score | 72.22 | 18 | Weakest broad axis. Selected trades often do not align cleanly with scanner/post-strategy leadership. |
| entry_timing_score | N/A | 0 | Historical June artifacts do not contain enough Q13 timing evidence. Do not infer good or bad timing from this range. |
| exit_horizon_score | 77.94 | 18 | Secondary weakness; several days show hold/exit horizon issues. |
| evidence_quality_score | 93.78 | 18 | Mostly usable, with some historical artifact gaps. |

Weakest-axis distribution:

- scanner_alignment_score: 9 days
- exit_horizon_score: 7 days
- selection_integrity_score: 1 day
- evidence_quality_score: 1 day

### 2026-06-01 to 2026-07-06

| Axis | Average Score | Scored Days | Interpretation |
| --- | ---: | ---: | --- |
| selection_integrity_score | 94.38 | 21 | Selection authority itself is mostly consistent. |
| scanner_alignment_score | 71.29 | 21 | Weakest aggregate axis. This remains the strongest evidence-backed suspect. |
| entry_timing_score | 92.00 | 3 | Only recent Q13-ready days are scored; not enough historical coverage for a broad conclusion. |
| exit_horizon_score | 75.52 | 21 | Second weakest broad axis. Exit/hold horizon remains a candidate after scanner alignment. |
| evidence_quality_score | 91.24 | 21 | Good enough for aggregate direction, but not perfect. |

Weakest-axis distribution:

- scanner_alignment_score: 10 days
- exit_horizon_score: 8 days
- selection_integrity_score: 1 day
- evidence_quality_score: 1 day
- entry_timing_score: 1 day

## Conclusion

Broader historical data is usable, and it changes the confidence level.

The main aggregate suspect is no longer "unknown" or only "entry timing." Across 74 trades, the broadest recurring weakness is scanner alignment:

- selected candidate not matching post-strategy top candidate
- selected rank not consistently near the strongest scanner candidate
- selection authority rows missing on some historical days

The second recurring weakness is exit horizon:

- before-min-hold candidates
- before-target-hold candidates
- cases where target hold would have improved outcome

Entry timing remains important, but June historical artifacts do not contain enough timing evidence to score it fairly. It should stay in the Q13 live observer for future data, not be treated as proven from June.

## Action Implication

Do not jump directly to an entry-timing behavior patch based on the historical range.

The next behavior-patch candidate should be selected from:

1. scanner alignment / selected-rank discipline
2. exit horizon / hold compliance

Entry timing should continue to collect evidence from Q13-ready data, but the broader June review does not support making it the first production behavior change.

