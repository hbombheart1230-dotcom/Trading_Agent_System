# Canonical Artifact Flow

## Why this layer exists
- Runtime nodes are the primary place where trading decisions are made.
- The system should capture those decisions once, at source, instead of rebuilding meaning later from mixed logs.
- Reporting and the operator UI are downstream readers.

## Canonical run artifacts
Per-run canonical JSON artifacts are written under:

`reports/canonical/<YYYY-MM-DD>/<run_id>/`

Files:
- `commander.json`
- `strategist.json`
- `scanner.json`
- `monitor.json`
- `supervisor.json`
- `executor.json`

These artifacts are additive. They do not replace existing state, traces, or report files.

## Reader precedence
Downstream readers should prefer:
1. canonical run artifacts
2. direct run/trade artifacts
3. event logs as fallback evidence

## Reporting impact
- `scripts/run_live_execution_bundle_report.py` now prefers canonical agent artifacts when building run snapshots and lifecycle bundles.
- `libs/reporting/trade_story_pipeline.py` carries canonical artifact references and provenance into trade story input.
- Trade-scope evidence metadata is additive under `reports/trades/<day>/<trade_id>/`:
  - `_provenance.json`
  - `_health.json`
  - `_artifact_links.json`
- Existing `report/trades` report files remain unchanged for backward compatibility.

## Operator UI impact
- `apps/operator_ui/data_access.py` now loads canonical run artifacts first through small adapters.
- Operator brief composition therefore starts from source-captured strategist/scanner/monitor/supervisor/executor summaries when available.

## Provenance
Downstream payloads now carry lightweight provenance metadata such as:
- `canonical`
- `direct_artifact`
- `event_log`

This keeps backward compatibility while making missing-source vs source-backed reasoning explicit.

## LLM Narrative Boundary
- Canonical artifacts are source-of-truth for decisions.
- LLM outputs (trade report, brief, daily summary) are narrative outputs that must read source evidence first.
- Partial/salvaged/fallback LLM states are explicit in artifacts and must not be treated as full success.
