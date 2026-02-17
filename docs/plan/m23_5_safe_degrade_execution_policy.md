# M23-5: Safe Degrade Execution Policy

- Date: 2026-02-17
- Goal: enforce execution-tightening policy when `state["resilience"]["degrade_mode"] == true`.

## Scope (minimal)

1. In degrade mode, block execution unless manual approval signal is explicitly present.
2. In degrade mode, require non-empty `SYMBOL_ALLOWLIST`.
3. In degrade mode, tighten effective notional guard to `25%` of `MAX_ORDER_NOTIONAL` (configurable ratio).

## Implemented

- File: `graphs/nodes/execute_from_packet.py`
  - Added degrade policy evaluation helper:
    - `_evaluate_degrade_execution_policy(...)`
  - Added policy checks:
    - manual approval required (`execution_manual_approved` / `manual_approved` / `exec_context.manual_approved`)
    - non-empty allowlist required (`SYMBOL_ALLOWLIST`)
    - allowlist symbol membership check in degrade mode
    - effective notional limit:
      - base: `MAX_ORDER_NOTIONAL`
      - ratio: `state["resilience_policy"]["degrade_notional_ratio"]` or `DEGRADE_NOTIONAL_RATIO` (default `0.25`)
  - Added explicit policy block logging:
    - `stage=execute_from_packet`, `event=degrade_policy_block`
  - Fixed blocked-reason normalization bug when `allow_result is None`.

- File: `tests/test_m23_5_safe_degrade_execution_policy.py`
  - Added regression tests:
    - manual approval required in degrade mode
    - allowlist required in degrade mode
    - tightened notional guard enforced in degrade mode
    - successful execution path when degrade policy passes

## Safety Notes

- This patch changes behavior only when `degrade_mode=true`.
- Normal mode execution path remains unchanged.
- Policy is intentionally conservative: missing manual approval or missing allowlist blocks execution.
