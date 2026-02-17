# M23-9: Commander Resilience Metrics Reporting

- Date: 2026-02-17
- Goal: expose commander resilience/cooldown/intervention/error aggregates in daily metrics report outputs.

## Scope (minimal)

1. Extend `generate_metrics_report` with `commander_resilience` summary block.
2. Keep JSON and markdown outputs in sync for operator visibility.
3. Add regression tests for both populated and empty-report schema cases.

## Implemented

- File: `scripts/generate_metrics_report.py`
  - Added `commander_resilience` JSON block:
    - `total`
    - `cooldown_transition_total`
    - `intervention_total`
    - `error_total`
    - `transition_total`
    - `runtime_status_total`
    - `cooldown_reason_total`
  - Aggregates from `stage=commander_router` events.
  - Added markdown section `## Commander Resilience`.

- File: `tests/test_m23_9_commander_resilience_metrics_report.py`
  - Added aggregation test for cooldown/resume/error commander events.
  - Added empty-report schema stability test.

## Safety Notes

- Observability-only change.
- No runtime routing/guard/execution behavior modifications.
