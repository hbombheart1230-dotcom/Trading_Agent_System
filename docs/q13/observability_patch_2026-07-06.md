# Post-Q9 Observability Patch - 2026-07-06

## Scope

This patch implements the agreed pre-behavior-change priorities:

1. Regenerate Q9 closure markdown from JSON ledger.
2. Add selection authority audit.
3. Add scanner score decomposition as observation-only fields.
4. Add horizon compliance report by strategy horizon and exit reason.

No entry rule, exit rule, scanner ranking rule, strategist prompt, Commander approval flow, or order execution behavior was changed.

## Added Outputs

Daily Q9 evaluation now writes:

- `reports/evaluation/daily/<day>/selection_authority_audit.json`
- `reports/evaluation/daily/<day>/selection_authority_audit.md`
- `reports/evaluation/daily/<day>/horizon_compliance_report.json`
- `reports/evaluation/daily/<day>/horizon_compliance_report.md`

Trade read models now include:

- `selection.score_decomposition.raw_scanner_top1`
- `selection.score_decomposition.post_strategy_top1`
- `selection.score_decomposition.selected_candidate`

Freeze window closeout now writes:

- `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/q9_closure_summary.md`
- `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/q9_closure_summary_<latest-day>.md`
- `daily_ledger.json.closure_markdown_drift_check`

## 2026-07-06 Verification

Q9 daily evaluation generated successfully for 2026-07-06:

- Trade count: 2
- `selection_authority_audit`: generated
- `horizon_compliance_report`: generated

Selection authority audit showed:

- `TRD_20260706_006800_01`
  - raw scanner top1: `006800`
  - post-strategy top1: `058400`
  - selected/executed: `006800`
  - Commander selected: `006800`
- `TRD_20260706_240810_01`
  - raw scanner top1: `240810`
  - post-strategy top1: `240810`
  - selected/executed: `240810`
  - Commander selected: `240810`

This means Commander did not change the executed symbol on these two trades. The 006800 case is a raw-vs-post-strategy ranking divergence plus selected-symbol execution, not evidence of Commander stock selection.

Horizon compliance audit showed:

- `intraday`, Kiwoom-reconciled SELL: 1 trade, before min hold 1, before target hold 1, target hold better 0, average return -0.9500%.
- `scalp`, Kiwoom-reconciled SELL: 1 trade, before min hold 1, before target hold 1, target hold better 0, average return -0.8200%.

This does not support a blanket "delay exits" behavior change.

## Verification Commands

Executed:

```powershell
venv\Scripts\python.exe -m pytest tests/test_q9_evaluation.py tests/test_historical_q9_prior.py -q
venv\Scripts\python.exe scripts\run_q9_evaluation.py --date 2026-07-06
```

Result:

- `16 passed`
- Q9 daily evaluation regenerated successfully.

Note:

- Full `run_frozen_q9_baseline_closeout.py` exceeded the 180 second command timeout because it rebuilds baseline/Q11/Q12 artifacts. The stale closure markdown was still corrected by regenerating from `daily_ledger.json` directly.

## Next Decision Gate

Before any behavior patch, inspect:

1. `selection_authority_audit` to decide whether the issue is raw scanner, post-strategy ranking, monitor/cascade, Commander, or execution.
2. `score_decomposition` to decide whether scanner score is overloaded or missing component fields.
3. `horizon_compliance_report` to decide whether a specific horizon/exit-reason pair supports delayed exit.

Only one behavior patch should be chosen after this review.

