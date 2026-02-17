# M25-1: Metric Schema Freeze v1

- Date: 2026-02-17
- Goal: freeze the minimum operator metric schema and add an automated validation gate.

## Scope (minimal)

1. Freeze schema baseline fields for operations:
   - `strategist_llm.success_rate`
   - `strategist_llm.latency_ms.p95`
   - `strategist_llm.circuit_open_rate`
   - `execution.intents_created/intents_approved/intents_blocked/intents_executed`
   - `execution.blocked_reason_topN`
   - `broker_api.api_error_total_by_api_id`
   - `broker_api.api_429_rate`
2. Add one CLI gate that validates required schema keys/types.
3. Add regression tests for pass/fail schema checks.

## Implemented

- File: `scripts/generate_metrics_report.py`
  - Added `schema_version = metrics.v1`.
  - Added `execution` block:
    - `intents_created`
    - `intents_approved`
    - `intents_blocked`
    - `intents_executed`
    - `blocked_reason_topN`
  - Added `broker_api` block:
    - `api_error_total_by_api_id`
    - `api_429_total`
    - `api_429_rate`
  - Kept legacy top-level metrics for backward compatibility.

- File: `scripts/check_metrics_schema_v1.py`
  - Generates daily metrics report and validates required v1 fields.
  - Return codes:
    - `0`: schema valid
    - `3`: schema invalid/missing required keys
    - `2`: metrics json read error

- File: `tests/test_generate_metrics_report.py`
  - Extended assertions for `schema_version`, `execution`, and `broker_api`.
  - Added `api_429_rate` aggregation regression test.

- File: `tests/test_m25_1_metrics_schema_freeze_v1.py`
  - Added pass-case validation test.
  - Added fail-case validation test for missing required keys.

## Safety Notes

- Observability-only milestone.
- Runtime order/approval/execution behavior is unchanged.
