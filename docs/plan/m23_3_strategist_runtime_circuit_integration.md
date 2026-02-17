# M23-3: Strategist Runtime Circuit Integration

- Date: 2026-02-17
- Goal: connect runtime-shared circuit breaker to strategist decision flow (`decide_trade`).

## Scope (minimal)

1. Apply runtime circuit gate before OpenAIStrategist call.
2. Update runtime circuit state on strategist success/failure.
3. Keep strategist telemetry compatible with existing circuit fields.

## Implemented

- File: `graphs/nodes/decide_trade.py`
  - Added runtime circuit integration using:
    - `gate_runtime_circuit(...)`
    - `mark_runtime_circuit_failure(...)`
    - `mark_runtime_circuit_success(...)`
  - Open-circuit path:
    - short-circuits strategist call
    - returns safe `NOOP` intent (`reason=circuit_open`)
  - Added compatibility sync for legacy top-level circuit fields:
    - `circuit_state`
    - `circuit_fail_count`
    - `circuit_open_until_epoch`

- File: `tests/test_m23_3_decide_trade_runtime_circuit_integration.py`
  - Added tests for:
    - second-call block when runtime circuit opens (`provider call count` stays unchanged)
    - half-open trial success closes and resets runtime circuit

## Safety Notes

- No execution guard precedence changes.
- No order routing changes.
- Circuit-open behavior remains advisory-safe (`NOOP`) and observable.
