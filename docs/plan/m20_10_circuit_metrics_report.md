# M20-10: Circuit Breaker Metrics in Daily Report

- Date: 2026-02-15
- Goal: include circuit breaker health signals in strategist LLM daily metrics summary.

## Scope (minimal)

1. Aggregate circuit breaker state/open metrics from `strategist_llm/result` events.
2. Add regression tests for new metric fields.

## Implemented

- File: `scripts/generate_metrics_report.py`
  - Added strategist LLM fields:
    - `circuit_open_total`
    - `circuit_open_rate`
    - `circuit_state_total`
  - Added markdown section under Strategist LLM:
    - `Circuit Breaker`

- File: `tests/test_generate_metrics_report.py`
  - Added coverage for circuit-open event aggregation.
  - Added empty-report schema checks for new keys.

## Safety Notes

- No execution path changes.
- No risk/guard behavior changes.
- Metrics-only enhancement for operator visibility.
