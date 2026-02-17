# M23-2: Runtime Circuit Breaker Core

- Date: 2026-02-17
- Goal: add a runtime-shared circuit breaker core utility for resilient routing decisions.

## Scope (minimal)

1. Add a core module that can:
   - gate requests based on circuit state/cooldown
   - mark failures and open the circuit on threshold
   - mark success and close/reset the circuit
2. Keep this milestone additive only (no execution path behavior change).
3. Add regression tests for open/half-open/close transitions.

## Implemented

- File: `libs/runtime/circuit_breaker.py`
  - Added `RuntimeCircuitPolicy(fail_threshold, cooldown_sec)`.
  - Added `gate_runtime_circuit(...)`.
  - Added `mark_runtime_circuit_failure(...)`.
  - Added `mark_runtime_circuit_success(...)`.
  - Uses canonical state contract via `ensure_runtime_resilience_state(...)`.
  - Supports env fallback policy keys:
    - `RUNTIME_CB_FAIL_THRESHOLD`
    - `RUNTIME_CB_COOLDOWN_SEC`
    - strategist compatibility fallback:
      - `AI_STRATEGIST_CB_FAIL_THRESHOLD`
      - `AI_STRATEGIST_CB_COOLDOWN_SEC`

- File: `tests/test_m23_2_runtime_circuit_breaker_core.py`
  - Added tests for:
    - open-circuit block before cooldown
    - open -> half-open transition after cooldown
    - failure threshold open behavior + resilience incident updates
    - success close/reset behavior

## Safety Notes

- Additive utility module only.
- No order execution guard behavior changes.
- No supervisor policy precedence changes.
