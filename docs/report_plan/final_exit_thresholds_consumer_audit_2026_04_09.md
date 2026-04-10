# Final Exit Thresholds Consumer Audit

## Purpose
List downstream readers that still primarily consume legacy `thresholds` surfaces instead of `final_exit_thresholds`.

## Current Canonical Source Of Truth
- Exit threshold source of truth: `final_exit_thresholds`
- Threshold provenance field: `exit_threshold_source`

The legacy `thresholds` object is still emitted for compatibility, but it should no longer be the preferred read path for exit-policy explanations.

## Priority Consumers To Migrate In Phase 2

### 1. `libs/reporting/trade_story_pipeline.py`
- Current pattern:
  - reads `monitor.get("thresholds")`
  - merges from `thresholds_guards_used.thresholds`
  - builds stop/take/peak-drawdown summary from the legacy threshold bag
- Why it matters:
  - this pipeline feeds trade-story/read-model surfaces that operators actually read
- Migration target:
  - prefer `monitor.get("final_exit_thresholds")`
  - preserve `thresholds_guards_used` only as compatibility fallback

### 2. `libs/reporting/trade_report_ai.py`
- Current pattern:
  - compacts `canonical_monitor.get("threshold_snapshot")`
  - uses `monitor_reason.get("thresholds_guards_used")`
  - still narrates legacy threshold surfaces in multiple sections
- Why it matters:
  - this is the most visible downstream consumer for trade explanations
- Migration target:
  - use `final_exit_thresholds` and `exit_threshold_source` first
  - keep legacy fields only as fallback/secondary context

### 3. `libs/reporting/agent_pipeline_trace.py`
- Current pattern:
  - renders `monitor.get("thresholds")` in trace markdown
- Why it matters:
  - trace output can drift from the effective threshold source if it keeps showing legacy bags first
- Migration target:
  - render `final_exit_thresholds` first

### 4. `libs/reporting/operator_visibility.py`
- Current pattern:
  - compacts nested `thresholds` values into technical evidence
- Why it matters:
  - summary surfaces should not imply that legacy threshold bags are still authoritative
- Migration target:
  - compact `final_exit_thresholds` first when present

### 5. `scripts/run_offhours_full_trace_bundle.py`
- Current pattern:
  - still prints `monitor.get("thresholds")`
- Why it matters:
  - off-hours debug bundles should match the canonical exit threshold source
- Migration target:
  - print `final_exit_thresholds` first, fallback to `thresholds`

## Compatibility Surfaces To Leave Alone For Now

### `libs/contracts/agent_outputs.py`
- This file intentionally emits both `thresholds` and `final_exit_thresholds` today.
- Recommendation:
  - keep both for compatibility
  - do not remove legacy `thresholds` yet
  - downstream readers should be migrated before any removal discussion

## Recommended Next Pass
1. Update `trade_story_pipeline` to prefer `final_exit_thresholds`
2. Update `trade_report_ai` to prefer `final_exit_thresholds`
3. Update trace/summary helpers (`agent_pipeline_trace`, `operator_visibility`, off-hours bundle)
4. Leave canonical artifact dual-emission in place until downstream migration is complete
