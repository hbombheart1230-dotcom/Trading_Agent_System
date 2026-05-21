# 2026-05-20 Quant Tactic Engine Q6

## Scope

Phase Q6 adds monitor-side quant decisions as diagnostic artifacts.

The goal is to make entry and exit reviews explicit without replacing the
existing monitor execution path in the same patch.

## Changes

- Added `libs/runtime/quant/decision.py`.
- Added `entry_quant_decision`:
  - tactic ID and playbook
  - cost edge state
  - cost-edge blocker
  - volume-confirmation blocker
  - directional-edge blocker
  - same-symbol-position blocker
  - pullback maturity warning or blocker depending on tactic
  - tactic suitability tier from scanner handoff
  - expected hold window
  - commander override requirement fields
- Added `exit_quant_decision`:
  - hard exit versus confirmation-required exit
  - early exit before expected minimum hold window
  - hold-window mismatch
  - cost-floor exit blockers
  - confirmation pending state for `intraday_low_break` and VWAP-style exits
  - exit versus strategy alignment reference
- Exposed decisions in:
  - `monitor_output`
  - `monitor_entry_decision_detail`
  - `monitor_exit_decision_detail`
  - `monitor_entry`
  - `monitor_exit`

## Behavior

No live entry, exit, ranking, or order behavior was changed.

The new fields are diagnostic:

```text
behavior_effect=observation_only
```

Important distinction:

- `intraday_low_break` and VWAP-style exits are treated as
  confirmation-required in the quant decision layer unless a hard invalidation
  or emergency flag is present.
- True hard exits remain allowed immediately.

## Operator Impact

Trade review can now separate:

- monitor wanted entry but quant diagnostics saw missing cost/volume edge
- monitor wanted exit but it was before expected hold window
- exit was a true hard stop versus an unconfirmed VWAP/low-break exit
- commander override would have been required for a weak or blocked entry

This should make the next report review more concrete without adding another
hidden behavior change.

## Validation

Passed:

```text
venv\Scripts\python.exe -m pytest -q tests/test_quant_decision.py tests/test_quant_factors.py tests/test_intraday_monitor_signals.py
83 passed

venv\Scripts\python.exe -m pytest -q tests/test_monitor_candidate_cascade.py tests/test_m21_commander_runtime_entry.py
92 passed
```

## Restart

No restart was performed for this refactor slice.

The running live process will not include these fields until restarted.

## Follow-Up

Next phase is Q7: report and memory feedback.

Q7 should surface these quant decisions in trade summaries/operator summaries
so failed trades can be grouped by tactic, cost edge, hold-window mismatch, and
exit confirmation quality.
