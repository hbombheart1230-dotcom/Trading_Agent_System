# 2026-08-31 Opening/Q10/Q12 Capture Alignment

## Scope

This patch repairs the operational wiring defects without changing the frozen
Q10 or Q12 signal thresholds.

## Opening Alpha

- The selected candidate's explicit rank remains authoritative when present.
- When that rank is absent, the controlled probe may use rank `1` only when the
  pre-Strategist Scanner authority artifact proves both intrinsic Rank-1 and
  symbol alignment.
- Missing or mismatched authority remains blocked.

## Q10 08:50 Capture

- `scripts/capture_q10_preopen_snapshot.py` performs the immutable lead-market
  capture independently of the 09:00 baseline loop.
- `scripts/run_mock_exam_preopen.bat` invokes it first under the existing 08:50
  Windows scheduled task.
- The canonical artifact remains:
  `reports/evaluation/baseline_samsung_hynix/YYYY-MM-DD/q10_forward_validation/q10_preopen_signal_snapshot.json`.

## Q12 08:55 Capture

- `scripts/run_q12_btc_0855_capture.bat` is registered as
  `TradingAgent-MockExamDay-Q12-BTC-0855` at 08:55 on weekdays.
- The capture retries only inside the point-in-time window and never performs
  post-window backfill.
- Frozen source evidence is reused by the normal Q12 loop.
- The snapshot and attempt ledger are written to:
  - `data/logs/q12_btc_0855/YYYY-MM-DD/btc_0855_snapshot.json`
  - `data/logs/q12_btc_0855/YYYY-MM-DD/capture_ledger.json`

## Independent Candidate Path

- Q10 Semiconductor, Q10 Index and Q12 BTC-Woori candidates are evaluated
  before the normal Strategist and Scanner cycle.
- A Strategist or Scanner early return therefore cannot suppress these fixed
  validation lanes.
- Existing-position exit handling still runs first. A controlled candidate
  cannot bypass portfolio, pending-order, restricted-symbol or same-symbol
  re-entry guards.
- If controlled-lane approval is rejected, the normal multi-agent cycle may
  continue. If an approved controlled order reaches the broker, that cycle ends
  after the broker result is recorded.

## Daily Evidence Ledgers

All controlled-lane evidence is stored under
`data/logs/controlled_mock_lanes/YYYY-MM-DD/`.

- `lane_evaluations.json`: `CANDIDATE_READY`, `NO_CANDIDATE`,
  `INPUT_MISSING`, guard blocks and approval rejects.
- `lane_attempts.json`: every order that reached the Executor, including broker
  rejection and the broker reason/code.
- `lane_submissions.json`: broker-accepted or filled orders only.

The one-order-per-lane daily limit reads only `lane_submissions.json`. Candidate
creation and Intent creation do not consume it. Broker rejection also does not
consume it, while the same immutable signal is not retried repeatedly.

## Preserved Guards

- Kiwoom mock mode only
- Existing risk-off and chart hard-floor blocks
- Existing cost-edge policy
- Existing position, pending-order and same-symbol guards
- One broker-accepted controlled submission per lane per day

## Verification

- Opening authority fallback, Q10 immutable capture, Q12 immutable capture,
  persisted-source reuse and controlled lane tests are deterministic.
- The integration test covers candidate generation, Intent creation, approval,
  mock broker request, broker acceptance, fill state and daily-limit recording.
- The Q12 task is enabled with its next run at 08:55 KST.
