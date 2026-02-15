# M20-8: Strategist Circuit Breaker + Safe Fallback

- Date: 2026-02-15
- Goal: prevent repeated strategist provider failures from causing continuous error loops.

## Scope (minimal)

1. Add circuit breaker in strategist provider only.
2. Keep failure behavior safe (`NOOP`) when circuit is open.
3. Add provider tests for open/recovery behavior.

## Implemented

- File: `libs/ai/providers/openai_provider.py`
  - Added env configs:
    - `AI_STRATEGIST_CB_FAIL_THRESHOLD`
    - `AI_STRATEGIST_CB_COOLDOWN_SEC`
  - Added circuit state machine (per `endpoint|model` key):
    - closed -> open (after threshold failures)
    - open -> closed (after cooldown)
  - Open-circuit behavior:
    - returns `NOOP` with `reason=circuit_open`
    - includes `error_type=CircuitOpen` and circuit metadata

- File: `tests/test_m20_1_openai_provider_smoke.py`
  - Added tests:
    - circuit opens after repeated failures and blocks following calls
    - circuit recovers after cooldown

## Safety Notes

- No execution path/guard precedence changes.
- Circuit-open path is advisory-safe fallback only (no order execution side effects).
