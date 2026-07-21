# Q13 Attribution Score Window Aggregate - 2026-06-29 ~ 2026-07-06

## Objective

Aggregate Q13 Attribution Score v0 across the full freeze window instead of reading a single day.

Inputs:

- `daily_ledger.json`
- per-day `attribution_score_v0.json`
- selection authority audit
- scanner score decomposition
- entry timing attribution
- horizon compliance report
- evidence quality / daily scorecard

Behavior effect:

- observation-only
- no trading behavior change
- invalid days are displayed but excluded from valid-day aggregate scores

## Generated Artifacts

- `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/attribution_score_window.json`
- `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/attribution_score_window.md`

## Coverage

| Item | Value |
| --- | ---: |
| Total days in ledger | 6 |
| Valid days | 5 |
| Attribution days available | 6 |
| Valid-day realized trades | 15 |

Notes:

- 2026-06-29 was invalid and excluded from aggregate conclusions.
- 2026-07-01 was valid but had 0 trades, so most causal axes are `INSUFFICIENT_EVIDENCE`.

## Aggregate Scores

| Axis | Avg Score | Min | Max | Scored Days | Insufficient Days |
| --- | ---: | ---: | ---: | ---: | ---: |
| selection_integrity_score | 93.75 | 90 | 100 | 4 | 1 |
| scanner_alignment_score | 54.25 | 20 | 92 | 4 | 1 |
| entry_timing_score | 92.00 | 76 | 100 | 3 | 2 |
| exit_horizon_score | 69.50 | 50 | 95 | 4 | 1 |
| evidence_quality_score | 82.00 | 50 | 100 | 4 | 1 |

## Weakest Axis Distribution

| Axis | Valid Days Weakest |
| --- | ---: |
| scanner_alignment_score | 2 |
| entry_timing_score | 1 |
| exit_horizon_score | 1 |

By average score, the weakest observed axis is:

- `scanner_alignment_score` at `54.25`

## Daily Rows

| Day | Valid | Trades | Weakest | Selection | Scanner | Entry | Exit/Horizon | Evidence |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2026-06-29 | no | 0 | - | - | - | - | - | - |
| 2026-06-30 | yes | 2 | scanner_alignment_score | 90 | 20 | - | 95 | 100 |
| 2026-07-01 | yes | 0 | - | - | - | - | - | - |
| 2026-07-02 | yes | 9 | entry_timing_score | 100 | 92 | 76 | 83 | 78 |
| 2026-07-03 | yes | 2 | scanner_alignment_score | 90 | 25 | 100 | 50 | 50 |
| 2026-07-06 | yes | 2 | exit_horizon_score | 95 | 80 | 100 | 50 | 100 |

## Interpretation

The freeze-window aggregate does not support entry timing as the dominant cause.

Current order of diagnostic suspicion:

1. `scanner_alignment_score`
   - Lowest average score.
   - Weakest axis on 2 valid trade days.
   - Repeated reasons include selected symbol not matching raw/post-strategy top1 and lower-rank execution.
2. `exit_horizon_score`
   - Not the lowest average, but repeatedly flags before-min/target-hold exits.
   - Weakest axis on 2026-07-06.
3. `entry_timing_score`
   - One weak day, but average remains high.
   - Entry timing is not cleared forever, but it is not the primary aggregate suspect.
4. `selection_integrity_score`
   - Mostly healthy.
   - Commander/execution symbol chain is not the dominant issue.
5. `evidence_quality_score`
   - Generally usable, but 2026-07-03 evidence quality was weak and should temper conclusions.

## Practical Conclusion

The next root-cause work should not start with entry delay.

The stronger aggregate hypothesis is:

> The system often loses edge when the executed/selected symbol is not aligned with raw or post-strategy scanner leadership, and losses are then amplified by exit/hold handling after early favorable movement fades.

This points Q14 toward a combined root-cause attribution layer:

- scanner alignment
- selected rank / cascade
- early MFE
- exit horizon violation
- realized loss
- evidence quality

Q15 should still choose exactly one behavior patch after Q14, not multiple simultaneous changes.

## Verification

Commands:

```powershell
venv\Scripts\python.exe -m pytest tests/test_attribution_score_window.py tests/test_attribution_score_v0.py tests/test_entry_timing_attribution.py -q
venv\Scripts\python.exe scripts\run_attribution_score_window.py --window-id q9_q10_q11_q12_5d_20260629
```

Result:

- `7 passed`
- window aggregate generated successfully

