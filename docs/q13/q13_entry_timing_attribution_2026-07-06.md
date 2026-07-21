# Q13 Entry Timing Attribution Patch - 2026-07-06

## Objective

Q13 extends the existing post-Q9 observability work. It does not change trading behavior.

Goal:

- Determine whether entry timing is a measurable cause of poor win rate.
- Quantify delay, immediate MFE/MAE, pre-entry missed move, and post-entry forward quality.
- Avoid changing entry, exit, scanner, strategist, Commander, or execution logic.

## Added Artifacts

Daily Q9 evaluation now also writes:

- `reports/evaluation/daily/YYYY-MM-DD/entry_timing_attribution_report.json`
- `reports/evaluation/daily/YYYY-MM-DD/entry_timing_attribution_report.md`

The report includes:

- scanner top1 time
- post-strategy top1 / strategist confirmation time
- selected candidate time
- actual entry time
- scanner/strategist/selected-to-entry delay
- entry +5m/+15m/+30m return
- MFE and MAE by horizon
- pre-entry move from Q9 decision time to actual entry
- automatic label:
  - `ENTRY_TOO_EARLY`
  - `ENTRY_TOO_LATE`
  - `ENTRY_APPROPRIATE`
  - `INSUFFICIENT_EVIDENCE`

## Label Policy

Labels are attribution hypotheses, not trading rules.

- `ENTRY_TOO_LATE`: meaningful pre-entry move already occurred and forward response is weak.
- `ENTRY_TOO_EARLY`: immediate adverse move after entry without prior alpha.
- `ENTRY_APPROPRIATE`: immediate forward response is favorable.
- `INSUFFICIENT_EVIDENCE`: missing timestamps, prices, or forward minute observations.

## 2026-07-06 Result

Generated report:

- `reports/evaluation/daily/2026-07-06/entry_timing_attribution_report.md`

Summary:

| Label | Trades | Avg Return | Avg Delay Sec | Avg 5m MFE | Avg 5m MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| ENTRY_TOO_EARLY | 0 | 0.0000% | - | - | - |
| ENTRY_TOO_LATE | 0 | 0.0000% | - | - | - |
| ENTRY_APPROPRIATE | 2 | -0.8850% | 0.5 | 0.8130% | -0.1121% |
| INSUFFICIENT_EVIDENCE | 0 | 0.0000% | - | - | - |

Trade details:

- `TRD_20260706_006800_01`
  - delay: 0 sec
  - pre-entry move: +0.0375%
  - +5m return: +0.5142%
  - +5m MFE: +1.0658%
  - +5m MAE: -0.1478%
  - label: `ENTRY_APPROPRIATE`
- `TRD_20260706_240810_01`
  - delay: 1 sec
  - pre-entry move: +0.0764%
  - +5m return: +0.1623%
  - +5m MFE: +0.5601%
  - +5m MAE: -0.0764%
  - label: `ENTRY_APPROPRIATE`

Interpretation:

- 2026-07-06 does not support entry timing delay as the primary cause.
- Both trades had favorable +5m response and low immediate adverse move.
- The realized losses came after the early favorable response faded.
- For this day, the next root-cause candidate is not raw entry timing. It is exit/hold/fade handling after early MFE.

## Verification

Commands:

```powershell
venv\Scripts\python.exe -m pytest tests/test_entry_timing_attribution.py tests/test_q9_evaluation.py -q
venv\Scripts\python.exe scripts\run_q9_evaluation.py --date 2026-07-06
```

Result:

- `17 passed`
- Q9 evaluation regenerated successfully.
- `entry_timing_attribution_report` generated with Q13 fields.

## Q13 Decision

Do not patch behavior from one day.

Q13 now provides the evidence surface needed to answer:

- Did we enter too late?
- Did we enter too early?
- Did the trade initially work, then fail due to hold/exit handling?

For 2026-07-06, the answer is:

- Entry timing was not the obvious primary failure.
- Early favorable movement existed.
- The stronger suspect is profit fade / exit timing after initial MFE.

