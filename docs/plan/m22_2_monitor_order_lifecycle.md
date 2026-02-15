# M22-2: Monitor Order Lifecycle Mapping

- Date: 2026-02-15
- Goal: convert `order.status` DTO signals into a canonical monitor lifecycle view with stage/progress/terminal flags.

## Scope (minimal)

1. Add lifecycle mapping in `monitor_node` from order status fields.
2. Keep existing intent generation contract unchanged.
3. Surface lifecycle in demo output and tests.

## Implemented

- File: `graphs/nodes/monitor_node.py`
  - Added lifecycle derivation from order status:
    - `working`
    - `partial_fill`
    - `filled`
    - `cancelled`
    - `rejected`
    - `unknown`
  - Added monitor fields:
    - `monitor.order_lifecycle_loaded`
    - `monitor.order_lifecycle`
      - `stage`, `terminal`, `progress`, `filled_qty`, `order_qty`

- File: `scripts/demo_m22_skill_flow.py`
  - Added top-level `order_lifecycle` summary output for quick operator visibility.

- File: `tests/test_m22_skill_native_scanner_monitor.py`
  - Added lifecycle assertions for:
    - partial fill
    - filled (qty progress)
    - cancelled
  - Added demo assertion for lifecycle stage output.

## Safety Notes

- No Supervisor/Executor guard behavior changed.
- No change to monitor intent shape (`state["intents"]`).
