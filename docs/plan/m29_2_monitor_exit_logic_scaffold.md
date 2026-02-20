# M29-2 Monitor Exit Logic Scaffold

## Goal
- Add minimal stop-loss / take-profit exit decision logic in Monitor.
- Keep existing behavior unchanged unless explicitly enabled.

## Implemented
- Added `libs/runtime/exit_policy.py`:
  - `evaluate_exit_policy(price, avg_price, qty, policy)`
  - deterministic result payload with:
    - `triggered`
    - `reason` (`stop_loss` | `take_profit` | `hold` | `no_position` | `price_unavailable`)
    - `pnl_ratio`
    - thresholds

- Integrated optional exit policy in `graphs/nodes/monitor_node.py`:
  - enable via:
    - `policy.use_exit_policy=true` or
    - `state.use_exit_policy=true`
  - when triggered:
    - replaces default BUY monitor intent with SELL exit intent (position qty)
  - added observability fields:
    - `state["monitor_exit"]`
    - `state["monitor"].exit_*`

## Compatibility
- Default is disabled.
- Existing monitor/scanner tests and runtime contracts are preserved.

## Tests
- Added:
  - `tests/test_m29_3_monitor_exit_policy.py`
- Coverage:
  - disabled mode keeps BUY intent
  - stop-loss SELL trigger
  - take-profit SELL trigger

