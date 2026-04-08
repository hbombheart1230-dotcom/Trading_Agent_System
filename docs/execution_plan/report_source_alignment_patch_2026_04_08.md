# Report Source Alignment Patch (2026-04-08)

## Scope
- Daytime-safe report and docs patch only
- Runtime trading semantics unchanged
- No changes to monitor order meaning, execution approval meaning, or guard precedence

## Route Aggregation Single Source of Truth
- Route aggregation now prefers `reports/canonical/<day>/<run_id>/commander.json`
- Canonical commander artifact is the single source of truth for:
  - `route_selected_total`
  - route breakdowns
  - strategist generation mode totals when available
- Event rows are fallback only when commander canonical artifacts are missing

## Route Provenance Metadata
- Reports now expose source provenance for route aggregation:
  - `route_source`
  - `route_source_run_count`
  - `route_source_missing_count`
  - `route_source_breakdown`
- Per-run route rendering in run cards prefers commander canonical data and surfaces the route source

## Daily Report / Operator Summary Decoupling
- `daily_report` no longer reads `operator_summary.json` as an input dependency
- `operator_summary` no longer reads `daily_report.json` for policy/chart executive summaries
- Both reports independently read canonical/event/trade artifacts and compute their own snapshots
- Shared read-only helpers are used so equal source windows produce nearly equal outputs

## Freshness and Stale Semantics
- Each report computes freshness from its own source window:
  - `generated_at`
  - `source_run_count`
  - `latest_run_id`
  - `latest_run_ts`
- Stale status is observational only
- If reports are generated at different times, stale differences should remain visible instead of being hidden

## Fallback Policy
- Commander route fallback order:
  1. canonical commander artifact
  2. commander event payload fallback
- Policy/chart executive summaries:
  - computed directly from canonical/event sources
  - degrade to empty-safe summaries if canonical monitor artifacts are unavailable

## Safety Notes
- This patch is additive only
- DTO/IO contracts remain backward compatible
- `reports/trades/*` storage structure is unchanged
- Logging and metadata remain observational only
