# M29-4 Monitor Metrics Reporting

## Goal
- Expose Monitor-side exit/sizing behavior in daily metrics reports.
- Keep `metrics.v1` compatibility while extending payload with additional monitor section.

## Implemented
- Updated `graphs/nodes/monitor_node.py`:
  - emits event log:
    - `stage="monitor"`
    - `event="summary"`
  - payload includes:
    - `exit_policy_enabled`, `exit_evaluated`, `exit_triggered`, `exit_reason`
    - `position_sizing_enabled`, `position_sizing_evaluated`, `position_sizing_qty`, `position_sizing_reason`

- Updated `scripts/generate_metrics_report.py`:
  - new summary section: `monitor_agent`
  - aggregated metrics:
    - `total`
    - `exit_policy_enabled_total`
    - `exit_evaluated_total`
    - `exit_trigger_total`
    - `exit_reason_total`
    - `position_sizing_enabled_total`
    - `position_sizing_evaluated_total`
    - `position_sizing_computed_qty_sum`
    - `position_sizing_zero_qty_total`
    - `position_sizing_reason_total`
  - markdown report now includes `## Monitor Agent` block.

## Tests
- Added `tests/test_m29_5_monitor_metrics_report.py`:
  - aggregation case
  - empty default schema case
- Full regression:
  - `353 passed`

