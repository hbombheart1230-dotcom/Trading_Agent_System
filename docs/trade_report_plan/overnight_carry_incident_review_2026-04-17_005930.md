# 2026-04-17 Samsung Overnight Carry Review

## Scope
- Symbol: `005930`
- Day: `2026-04-17`
- Focus: whether the overnight hold was a valid carry approval or a missing closeout decision

## Conclusion
- This was not a valid carry approval.
- The position remained open while `minutes_to_close` was missing in monitor-time artifacts.
- Under the new contract this case should be treated as an overnight-carry anomaly, not as an approved carry.

## Entry evidence
- Entry BUY run: `reports/canonical/2026-04-17/34216402960a47b99b8ca933281527c9/executor.json`
- Observed:
  - `symbol = 005930`
  - `action = BUY`
  - `execution_ok = true`

## Representative monitor runs
1. `reports/canonical/2026-04-17/151ad670270a4d6f84e647c50d59892d/monitor.json`
- `ts = 2026-04-17T03:39:26+00:00`
- `decision = NOOP`
- `monitor_reason = hold`
- `minutes_to_close = null`

2. `reports/canonical/2026-04-17/00c68988133b41fc9a62cb8fa6aa9bdb/monitor.json`
- `ts = 2026-04-17T05:36:25+00:00`
- `decision = NOOP`
- `monitor_reason = hold`
- `minutes_to_close = null`

3. `reports/canonical/2026-04-17/0c014d44ae8a40bf979cbf53adbcc29d/monitor.json`
- `ts = 2026-04-17T05:52:25+00:00`
- `decision = NOOP`
- `monitor_reason = hold`
- `minutes_to_close = null`

## Observed scale
- `005930` monitor artifacts with `minutes_to_close = null` on `2026-04-17`: `199`

## Root cause
- `monitor_node` and closeout guard already consumed `state["market_context"]["minutes_to_close"]`.
- The live runtime did not reliably populate that field before the recent fix.
- As a result:
  - overnight carry evaluation did not run
  - carry approval was not explicitly recorded
  - the open position simply survived into the next day

## Fixes now in place
1. `graphs/commander_runtime.py`
- backfills `market_context.minutes_to_close` from runtime clock

2. `graphs/nodes/monitor_node.py`
- records:
  - `eod_carry_anomaly`
  - `eod_carry_anomaly_reason`
- anomaly reason:
  - `minutes_to_close_missing`

3. `scripts/run_mock_exam_day.py`
- closeout backup no longer respects anomalous carry approvals
- anomalous carry is flattened instead of carried forward

4. `libs/reporting/trade_story_pipeline.py`
- trade-report monitor reasoning now surfaces overnight carry anomaly explicitly

## Expected behavior after fix
- Valid carry:
  - `eod_carry_evaluated = true`
  - `eod_carry_approved = true`
- Valid flatten:
  - `eod_carry_evaluated = true`
  - `eod_carry_approved = false`
- Invalid/missing evaluation:
  - `eod_carry_evaluated = false`
  - `eod_carry_anomaly = true`
  - `eod_carry_anomaly_reason = "minutes_to_close_missing"`
