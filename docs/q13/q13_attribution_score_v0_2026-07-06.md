# Q13 Attribution Score v0 - 2026-07-06

## Objective

Q13 now combines existing post-Q9 evidence surfaces into one simple diagnostic scorecard.

Inputs:

- daily ledger
- selection authority audit
- scanner score decomposition
- horizon compliance report
- entry timing attribution report
- daily scorecard / artifact integrity

Behavior effect:

- observation-only
- no entry logic changes
- no exit logic changes
- no scanner ranking changes
- no strategist/Commander prompt or approval changes

## Scores

Each axis is scored from 0 to 100.

If evidence is missing, the axis is marked `INSUFFICIENT_EVIDENCE` instead of being assigned a low score.

| Axis | Meaning |
| --- | --- |
| `selection_integrity_score` | Whether selected/executed symbols stayed consistent through selection, monitor, Commander, and execution. |
| `scanner_alignment_score` | Whether executed candidates aligned with raw/post-strategy scanner ranking. |
| `entry_timing_score` | Whether entries were too early, too late, or had favorable immediate response. |
| `exit_horizon_score` | Whether exits respected strategy horizon and whether target hold would have improved outcome. |
| `evidence_quality_score` | Whether artifacts and Q9 evidence surfaces are complete enough to trust the diagnosis. |

## 2026-07-06 Result

Generated:

- `reports/evaluation/daily/2026-07-06/attribution_score_v0.json`
- `reports/evaluation/daily/2026-07-06/attribution_score_v0.md`

Scores:

| Axis | Score | Interpretation |
| --- | ---: | --- |
| selection_integrity_score | 95 | Selection chain mostly intact. Commander did not change executed symbol. |
| scanner_alignment_score | 80 | One trade selected rank2 / not post-strategy top1, so scanner alignment is a secondary suspect. |
| entry_timing_score | 100 | Entry timing was not the observed primary failure on 7/6. |
| exit_horizon_score | 50 | Weakest observed axis. Both trades exited before min/target hold. |
| evidence_quality_score | 100 | Evidence surfaces were complete for this diagnosis. |

Weakest observed axis:

- `exit_horizon_score`

## Interpretation

For 2026-07-06, the evidence says:

1. Entry timing was not the main failure.
2. Both entries had favorable early response.
3. Both trades ended as realized losses.
4. Both trades violated strategy horizon timing.
5. The next root-cause candidate is exit/hold/fade handling, not raw entry delay.

Important caveat:

- `exit_horizon_score` being low does not automatically authorize "hold longer".
- It means Q14 should combine:
  - early MFE,
  - realized loss,
  - before-min/target hold,
  - target-hold counterfactual,
  - exit reason,
  into a single root-cause attribution.

## Verification

Commands:

```powershell
venv\Scripts\python.exe -m pytest tests/test_attribution_score_v0.py tests/test_entry_timing_attribution.py tests/test_q9_evaluation.py -q
venv\Scripts\python.exe scripts\run_q9_evaluation.py --date 2026-07-06
```

Result:

- `20 passed`
- Q9 evaluation regenerated successfully.
- `attribution_score_v0` generated successfully.

