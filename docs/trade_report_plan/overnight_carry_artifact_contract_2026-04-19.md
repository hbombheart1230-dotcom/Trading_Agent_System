# Overnight Carry Artifact Contract

## Purpose
- Make overnight carry decisions explicit in `monitor.json`.
- Separate three cases:
  - carry approved
  - flatten before close
  - carry evaluation anomaly

## Expected monitor fields
- `minutes_to_close`
- `eod_flat_cutoff_min`
- `eod_carry_evaluated`
- `eod_carry_approved`
- `eod_carry_action`
- `eod_carry_reason`
- `eod_carry_positive_signals`
- `eod_carry_blockers`
- `eod_carry_non_eod_reason`
- `eod_carry_non_eod_triggered`
- `eod_carry_anomaly`
- `eod_carry_anomaly_reason`

## Normal cases
1. Carry approved
- `eod_carry_evaluated = true`
- `eod_carry_approved = true`
- `eod_carry_action = "carry_overnight"`
- `monitor_reason = "eod_carry_approved"`

2. Flatten before close
- `eod_carry_evaluated = true`
- `eod_carry_approved = false`
- `eod_carry_action = "flatten_before_close"`
- `reason = "eod_flat"` or a stronger exit reason

3. Outside closeout window
- `eod_carry_evaluated = false`
- `eod_carry_anomaly = false`
- `minutes_to_close > cutoff_min`

## Anomaly case
- Definition:
  - open position exists
  - `use_eod_flat = true`
  - but `minutes_to_close` is missing
- Expected fields:
  - `eod_carry_evaluated = false`
  - `eod_carry_anomaly = true`
  - `eod_carry_anomaly_reason = "minutes_to_close_missing"`

## 2026-04-17 Samsung root cause
- The Samsung overnight case was not an explicit carry approval.
- `minutes_to_close` was missing in the runtime state, so carry evaluation did not run.
- This document defines that case as an anomaly, not a valid carry decision.
