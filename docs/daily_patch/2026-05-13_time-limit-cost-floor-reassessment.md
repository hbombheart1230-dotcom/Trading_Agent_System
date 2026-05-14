# 2026-05-13 Time Limit / Cost Floor Reassessment

## Context

- Today's trades repeatedly showed small gross gains turning into net losses after fees/tax.
- `max_hold=900` was acting like a hard SELL trigger for scalp horizon trades.
- That made time-based exits bypass the cost-aware profit floor, even when the trade had not cleared the required round-trip cost plus buffer.
- Some reports also showed `SELL was triggered because hold`, which is not a valid confirmed monitor exit trigger.

## Patch

- `max_hold_sec` / `time_stop_sec` are now treated as time-limit reassessment triggers when cost-aware profit floor is enabled.
- Time-limit exits are only allowed when the effective exit PnL clears the cost-aware floor.
- If the time limit is reached but profit floor is not met:
  - the monitor keeps `reason=hold`
  - records `time_limit_reassessment_blocked=true`
  - records `hold_block_reason=max_hold:cost_aware_profit_floor_not_met`, `time_stop:cost_aware_profit_floor_not_met`, or `max_hold:time_limit_reached_without_profit_floor`
- Exceptions still remain intact:
  - hard stop
  - stop loss
  - emergency halt
  - EOD flat / closeout
  - confirmed hard structural invalidation such as explicit hard VWAP breakdown
- Monitor/report artifacts now expose:
  - `hold_limit_sec`
  - `max_hold_reached`
  - `time_stop_reached`
  - `time_limit_reached`
  - `time_limit_reassessment_required`
  - `time_limit_reassessment_blocked`
  - `time_limit_reassessment_blocked_reason`
- Entry reward-room hard guard was tightened around the cost floor:
  - if `reward_room_pct < 0.012` and the entry is late/near upper zone, BUY is blocked before order submission
  - clean non-late pullback/reversion setups are not blanket-blocked
- Report summary logic now treats SELL + monitor `hold` + `exit_triggered=false` as a monitor/executor mismatch, not as a valid `SELL because hold` trigger.

## Verification

- `venv\\Scripts\\python.exe -m pytest tests/test_strategy_sizing_exit_upgrade.py tests/test_m29_3_monitor_exit_policy.py tests/test_monitor_exit_guard.py tests/test_execute_from_packet.py tests/test_intraday_monitor_signals.py tests/test_trade_story_pipeline_enrichment.py tests/test_canonical_artifact_validation.py`
- Result: `309 passed`.

## Live Check

- Next live run should verify:
  - 900-second scalp time limit no longer sells small gross-profit trades below the 1.2% cost-aware floor.
  - Reports show time-limit reassessment fields instead of hiding `max_hold`.
  - Late entries with less than 1.2% reward room are blocked before order submission.
  - `SELL because hold` does not appear as a confirmed trigger.

