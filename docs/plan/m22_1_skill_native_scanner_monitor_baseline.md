# M22-1: Skill-Native Scanner/Monitor Baseline + Visible Demo

- Date: 2026-02-15
- Goal: make Scanner/Monitor consume skill DTO inputs (`market.quote`, `account.orders`, `order.status`) while preserving existing default behavior.

## Scope (minimal)

1. Add optional skill DTO read path to `scanner_node`.
2. Add optional `order.status` observation path to `monitor_node`.
3. Keep legacy behavior unchanged when skill data is absent.
4. Provide one offline demo script that shows visible output.

## Implemented

- File: `graphs/nodes/scanner_node.py`
  - Added optional skill input readers:
    - `market.quote` (`skill_results` / `skill_data` aliases)
    - `account.orders`
  - Added skill-derived features in `scan_results[*].features`:
    - `skill_quote_price`
    - `skill_open_orders`
  - Added conservative skill adjustments to score/risk/confidence.
  - Added scanner-level summary:
    - `state["scanner_skill"]`

- File: `graphs/nodes/monitor_node.py`
  - Added optional `order.status` summary extraction.
  - Added monitor-level fields:
    - `monitor.order_status_loaded`
    - `monitor.order_status`
  - Intent generation contract remains unchanged.

- File: `scripts/demo_m22_skill_flow.py`
  - Added offline runnable demo for skill-native scanner/monitor path.
  - Outputs selected symbol, top candidates, skill summary, and monitor order status.

- File: `tests/test_m22_skill_native_scanner_monitor.py`
  - Added coverage for scanner skill penalty path.
  - Added coverage for monitor order-status attachment path.
  - Added demo-script JSON output contract test.

## Safety Notes

- Existing path remains default-safe with no skill input.
- No approval/execution guard behavior changed.
