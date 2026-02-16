# M22-4: Skill DTO Contract Standardization for Scanner/Monitor

- Date: 2026-02-15
- Goal: freeze one shared skill DTO consumption contract (`m22.skill.v1`) across Scanner and Monitor nodes.

## Scope (minimal)

1. Add shared contract adapter module for skill payload extraction.
2. Remove duplicate ad-hoc parsing logic across nodes.
3. Expose contract version in node output metadata.
4. Add unit tests for contract adapter behavior.

## Implemented

- File: `graphs/nodes/skill_contracts.py`
  - Added shared contract version constant:
    - `CONTRACT_VERSION = "m22.skill.v1"`
  - Added normalized extraction helpers:
    - `extract_market_quotes(state)`
    - `extract_account_orders_rows(state)`
    - `extract_order_status(state)`
  - Standardized result meta:
    - `contract_version`
    - `present`
    - `used`
    - `errors`
  - Preserved readiness/error wrapper handling (`error` / `ask` / `result.data` / `data`).

- File: `graphs/nodes/scanner_node.py`
  - Switched skill parsing to shared contract module.
  - Added `scanner_skill.contract_version`.

- File: `graphs/nodes/monitor_node.py`
  - Switched order status parsing to shared contract module.
  - Added `monitor.skill_contract_version`.

- File: `scripts/demo_m22_skill_flow.py`
  - Added contract version summary output for scanner/monitor.

- File: `tests/test_m22_skill_contracts.py`
  - Added contract extraction tests for quote/orders/status paths.
  - Added contract violation test.

## Safety Notes

- Existing fallback semantics are preserved.
- No Supervisor/Executor behavior changed.
