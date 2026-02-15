# M20-9: Circuit Breaker Event Visibility

- Date: 2026-02-15
- Goal: expose strategist circuit breaker status in `strategist_llm` telemetry so operators can verify open/closed behavior from logs.

## Scope (minimal)

1. Add circuit breaker fields to `strategist_llm/result` event payload.
2. Add regression test for circuit-open event visibility.

## Implemented

- File: `graphs/nodes/decide_trade.py`
  - Added payload propagation for:
    - `circuit_state`
    - `circuit_fail_count`
    - `circuit_open_until_epoch`

- File: `tests/test_m20_3_llm_event_logging.py`
  - Added `test_m20_9_llm_event_logs_circuit_breaker_fields`
  - Verifies `CircuitOpen` event telemetry fields on repeated failing calls.

## Safety Notes

- No execution path changes.
- No guard precedence changes.
- Observability-only addition.
