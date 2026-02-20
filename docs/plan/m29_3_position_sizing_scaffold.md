# M29-3 Position Sizing Scaffold

## Goal
- Add optional risk-based position sizing to Monitor entry intents.
- Preserve existing behavior by default.

## Implemented
- Added `libs/runtime/position_sizing.py`:
  - `evaluate_position_size(price, cash, policy, risk_context)`
  - deterministic qty decision using:
    - `risk_per_trade_ratio`
    - `stop_loss_pct`
    - `position_notional_ratio`
    - optional `lot_size`, `min_position_qty`, `max_position_qty`

- Updated `graphs/nodes/monitor_node.py`:
  - `use_position_sizing=true` (state/policy) enables sizing logic.
  - BUY intent qty now comes from sizing decision when enabled.
  - If computed qty is 0, entry intent is suppressed.
  - Added monitor observability:
    - `state["monitor_sizing"]`
    - `state["monitor"].position_sizing_*`

## Compatibility
- Default remains unchanged (`qty=1` when sizing disabled).
- Existing monitor/scanner contracts remain valid.

## Tests
- Added `tests/test_m29_4_monitor_position_sizing.py`.
- Verified:
  - disabled mode keeps default qty
  - enabled mode produces risk-based qty
  - low-cash case suppresses entry intent
- Full suite status:
  - `351 passed`

