# M22-9: Hydration Metrics and Reporting Integration

- Date: 2026-02-16
- Goal: expose skill hydration/fallback behavior in daily metrics so operators can monitor M22 reliability in one report.

## Scope (minimal)

1. Emit hydration summary events from the hydration node.
2. Aggregate hydration metrics in `generate_metrics_report`.
3. Keep existing metrics schema backward compatible (additive fields only).

## Implemented

- File: `graphs/nodes/hydrate_skill_results_node.py`
  - Added `skill_hydration/summary` event emission.
  - Event payload uses `state["skill_fetch"]` contract and includes runner source/fetch stats.

- File: `scripts/generate_metrics_report.py`
  - Added `skill_hydration` section:
    - `total`
    - `used_runner_total`
    - `fallback_hint_total`
    - `fallback_hint_rate`
    - `errors_total_sum`
    - `runner_source_total`
    - `attempted_total_by_skill`
    - `ready_total_by_skill`
    - `errors_total_by_skill`
  - Added markdown rendering for hydration metrics.
  - Added empty-schema defaults for new keys.

- File: `tests/test_generate_metrics_report.py`
  - Added hydration event fixtures and assertions for aggregated values.
  - Added empty-report schema assertions for hydration keys.

- File: `tests/test_m22_skill_hydration_node.py`
  - Added event logging test for `skill_hydration/summary`.

## Safety Notes

- Metrics change is additive; existing fields are preserved.
- Logging failures are non-fatal and do not block runtime flow.
