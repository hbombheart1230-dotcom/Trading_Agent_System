# 2026-05-20 Quant Tactic Engine Q7 Slice 1

## Scope

Q7 Slice 1 surfaces the Q5/Q6 quant diagnostics in trade reports.

This slice focuses on report visibility only. Operator weekly aggregation and
structured memory feedback remain separate Q7 slices.

## Changes

- Added `libs/reporting/quant_tactic_report.py`.
- Added a reusable quant tactic report surface:
  - tactic ID
  - playbook
  - scanner tactic suitability
  - entry quant decision
  - exit quant decision
  - cost edge
  - expected hold window versus actual hold time
  - factor snapshot highlights
- Added `## 전술/퀀트 진단` to full trade reports.
- Added compact quant tactic diagnostics to trade summaries.
- Propagated quant decisions through `build_monitor_reason_human`.
- Preserved quant fields in deterministic monitor snapshots.

## Behavior

No trading behavior changed.

This is a reporting and memory-readiness patch. It makes the following review
questions answerable directly from the report:

- Was this symbol tactic-fit or only scanner-ranked high?
- Did entry diagnostics see cost or volume blockers?
- Would commander override have been required?
- Was the exit a true hard exit or a confirmation-required exit?
- Was the exit earlier than the tactic's expected minimum hold window?

## Validation

Passed:

```text
venv\Scripts\python.exe -m pytest -q tests/test_quant_tactic_report.py tests/test_quant_decision.py tests/test_trade_report_ai.py
136 passed

venv\Scripts\python.exe -m pytest -q tests/test_trade_lifecycle_builder.py tests/test_intraday_trade_reports.py
28 passed
```

## Restart

No restart was performed.

The running process will not include the new report fields until restarted and
new report artifacts are generated.

## Next

Q7 remaining slices:

- Strategist LLM summary exposure of quant context usage.
- Operator daily/weekly aggregation by tactic, cost edge, hold window, and exit
  confirmation quality.
- Structured memory feedback tags for future strategy scoring.
