# M22-3: Skill Timeout/Error Fallback Quality Gates

- Date: 2026-02-15
- Goal: enforce safe fallback behavior when skill DTO inputs are unavailable or failed (`timeout/error/ask/invalid-shape`).

## Scope (minimal)

1. Add skill payload readiness/error detection to Scanner and Monitor.
2. Ensure runtime continues with baseline logic when skill inputs fail.
3. Expose fallback metadata for operators/tests.
4. Extend demo script with timeout simulation mode.

## Implemented

- File: `graphs/nodes/scanner_node.py`
  - Added skill payload unwrapping and readiness checks for:
    - `market.quote`
    - `account.orders`
  - Added fallback metadata in `state["scanner_skill"]`:
    - `fallback`
    - `fallback_reasons`
    - `error_count`
    - `quote_present`
    - `account_orders_present`
  - Baseline candidate scoring remains active when skill inputs fail.

- File: `graphs/nodes/monitor_node.py`
  - Added skill payload unwrapping and readiness checks for:
    - `order.status`
  - Added monitor fallback metadata:
    - `order_status_present`
    - `order_status_fallback`
    - `order_status_fallback_reasons`
    - `order_status_error_count`
  - Lifecycle derivation runs only when valid status payload is available.

- File: `scripts/demo_m22_skill_flow.py`
  - Added `--simulate-timeout` mode to visualize fallback behavior.

- File: `tests/test_m22_skill_native_scanner_monitor.py`
  - Added timeout/error fallback tests for scanner and monitor.
  - Added demo timeout simulation assertion.

## Safety Notes

- No execution/approval guard behavior changed.
- Fallback path is additive and defaults to prior baseline behavior.
