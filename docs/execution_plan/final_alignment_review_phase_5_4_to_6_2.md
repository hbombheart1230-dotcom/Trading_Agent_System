# Final Alignment Review: Phase 5-4 to 6-2 Operational Baseline

## Summary
This document records the current operational baseline across Phase 5-4 through Phase 6-2 after the post-market report/doc alignment patches.

## What Is Aligned
- Commander route source / route provenance:
  - single source of truth: `reports/canonical/<day>/<run_id>/commander.json`
  - fallback policy: event fallback only when canonical commander artifacts are missing
- Daily/operator independence:
  - `daily_report` and `operator_summary` are generated independently from shared read-only helpers
  - neither report needs to read the other report file to build its own summary
- Trade explain alignment:
  - official operator-facing output path: `reports/dev/analysis/trade_explain/*`
  - custom output paths remain allowed for ad-hoc generation, but they are non-canonical
- Narrative axis:
  - entry-first display for BUY / WAIT / NO_TRADE surfaces
  - exit-first display for SELL / EXIT surfaces
  - primary explanation is chosen by axis, with the opposite-side context kept secondary
- Freshness and stale semantics:
  - operator-facing reports expose generated time, source run count, latest run id, latest run timestamp, freshness status, stale flag, and stale reason
  - source differences caused by generation timing are surfaced instead of hidden

## Runtime Semantics Unchanged
The following non-negotiable runtime rules remain unchanged:
- Monitor must never place orders
- Execution layer must never execute without approval
- Guards override approvals
- Approval / execution / risk semantics are unchanged
- DTO/IO compatibility remains additive-only
- Reporting and logging remain observational only

## Official Report Path Baseline
- `daily_report`: `reports/daily/<day>/daily_report.json|md`
- `operator_summary`: `reports/daily/<day>/operator_summary.json|md`
- `metrics`: `reports/metrics/metrics_<day>.json|md`
- `decision_story`: `reports/dev/manual/decision_story/decision_story_<day>.md`
- `run_cards`: `reports/dev/manual/run_cards/run_cards_<day>.md`
- `trade_explain`: `reports/dev/analysis/trade_explain/trade_explain_<day>.json|md`

## Remaining Gaps
- Older or sparse runs can still require event fallback for route provenance.
- Some report sections remain limited by upstream payload richness.
- Separate report generation times can still lead to stale summaries; freshness metadata is the intended way to interpret that difference.
- Historical closeout notes may describe the earlier rollout state, while this document describes the current operational baseline.

## Current Operational Reading Order
1. canonical artifact for run-level truth
2. metrics / daily / operator summary for aggregation
3. decision story / run cards / trade explain for operator-facing explanation

This is the baseline to use when comparing current code, reports, and operator-facing documentation.
