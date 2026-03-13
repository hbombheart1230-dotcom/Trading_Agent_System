# M31-19 Trade Reconciliation and Exit Guard Harmonization

- Date: 2026-03-13
- Goal: reduce confusing broker trade history and make local observability explain it.

## Problem

- Mock broker account history showed dense BUY/SELL churn that was hard to explain from operator reports.
- Runtime allowed contradictory config such as:
  - `MIN_HOLD_SECONDS=600`
  - `EXIT_POLICY_MAX_HOLD_SEC=60`
- In that setup, the first sell-eligible tick after min-hold can flatten immediately, which makes the monitor policy look inconsistent.
- Local `events.jsonl` also had no dedicated broker reconciliation view, so broker-side rows and local executions were not compared directly.

## Changes

1. Monitor harmonizes time-based exit thresholds against effective min-hold.
   - If `max_hold_sec` or `time_stop_sec` is shorter than effective `min_hold_sec`, the monitor raises that threshold to min-hold instead of allowing contradictory behavior.
2. Monitor summary events now expose:
   - `position_age_seconds`
   - `min_hold_sec`
   - `sell_cooldown_sec`
   - `exit_confirm_ticks`
   - `exit_confirm_count`
   - `min_hold_blocked`
   - `sell_cooldown_blocked`
   - `sell_guard_reason`
   - `exit_policy_guard_adjustments`
3. Added broker reconciliation script:
   - `scripts/run_broker_trade_reconciliation.py`
   - reads Kiwoom mock broker fill history (`kt00009`)
   - compares broker `ord_no` rows against local `execute_from_packet` execution events
   - writes JSON/MD reports under `reports/reconciliation/`

## Operational Use

```powershell
python -m scripts.run_broker_trade_reconciliation --day 2026-03-13 --event-log-path data/logs/events.jsonl
```

Outputs:

- `reports/reconciliation/broker_trade_reconciliation_<day>.json`
- `reports/reconciliation/broker_trade_reconciliation_<day>.md`

## Expected Outcome

- Contradictory time-stop settings no longer create immediate post-hold exits.
- Operators can compare broker-side trade history with local execution logs by `ord_no`.
- When the broker UI shows rows that local reports do not explain, the mismatch is now explicit instead of implicit.
