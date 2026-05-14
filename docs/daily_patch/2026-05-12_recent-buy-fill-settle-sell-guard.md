# 2026-05-12 Recent Buy Fill-Settle Sell Guard

## Reason

003060 was bought with a 1,000-share order, but the next account snapshot briefly showed only `qty=1`. The monitor then emitted a structural SELL (`vwap_breakdown`) against that 1-share partial reflection.

This is unsafe because a just-submitted buy can be partially filled or partially reflected by the account reader before the full order settles. Structural exits such as VWAP breakdown should not immediately liquidate that partial snapshot unless the exit is a true emergency/stop.

## Patch

- Added an execution guard for SELL orders while a same-symbol recent BUY guard is still active.
- If the recent BUY quantity is larger than the reflected position quantity, structural SELL reasons are blocked with:
  - `sell_guard_recent_buy_fill_settle_partial_position`
- Emergency exits remain allowed during the fill-settle window:
  - `emergency_halt`
  - `news_shock`
  - `hard_stop`
  - `stop_loss`
  - `eod_flat`
- Existing partial-profit behavior after the full position is reflected remains allowed.
- Reordered execution guards so known mock-broker restricted symbols report `mock_broker_restricted_symbol_blocked` before the generic asset-universe guard.

## Validation

- `.\venv\Scripts\python.exe -m py_compile graphs\nodes\execute_from_packet.py graphs\nodes\monitor_node.py libs\runtime\exit_policy.py` passed.
- `.\venv\Scripts\python.exe -m pytest -q tests\test_execute_from_packet.py` passed: 35 passed.
- `.\venv\Scripts\python.exe -m pytest -q tests\test_monitor_exit_guard.py` passed: 100 passed.

## Live Check

If a large BUY is followed by a partial position snapshot such as `qty=1`, VWAP/structure-based SELL should be blocked until the position is fully reflected or the recent-buy guard expires. Stop-loss and emergency exits are still allowed.
