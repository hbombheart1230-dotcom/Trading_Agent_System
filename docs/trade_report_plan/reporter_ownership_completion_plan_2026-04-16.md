# Reporter Ownership Completion Plan (2026-04-16)

## Goal

This document fixes one question only:

- who decides that a report is needed
- who owns each reporting lane
- which modules are real owners
- which scripts must be reduced to thin boundaries

This is not a trade-report core refactor document.
This is not a report-surface pruning document.

Those responsibilities stay in:

- `docs/trade_report_plan/trade_report_runtime_guardrails_2026-04-16.md`
- `docs/trade_report_plan/report_surface_pruning_2026-04-16.md`

This document is the ownership map.

## Current Problem

`Reporter` exists as a name, but ownership is still split.

Today the system looks like this:

- `graphs/nodes/reporter_node.py` is a thin adapter
- `libs/agent/reporter.py` is mostly a facade
- `libs/reporting/intraday_trade_reports.py` owns part of live trade-report orchestration
- `scripts/run_live_execution_bundle_report.py` still owns a large part of live trade-report runtime flow
- `scripts/run_mock_exam_day.py` still owns closeout orchestration
- `scripts/run_live_session_watch.py` and `scripts/run_live_session_summary.py` still own session monitoring outputs

The result is not "one reporter agent".
It is "multiple owners under the reporter name".

## What This Means In Practice

The problem is not that every report type is different.
Different report lanes are normal.

The problem is that each lane does not yet have one clear owner.

That is why:

- `reports/` keeps accumulating legacy roots and fallback paths
- live and batch drift from each other
- script-to-script execution survives longer than it should
- operators see Reporter as a domain, but the code still behaves like several wrappers and scripts

## Decision Rule

The correct split is:

1. `Commander` decides whether reporting work should be requested
2. `Reporter` owns reporting lanes
3. `Monitoring` owns session telemetry lanes
4. `scripts/*` remain CLI and process boundaries only

This means `Commander` should own report intent, not report assembly.

## Commander-Owned Intents

`Commander` should decide only at the intent level.

Recommended intents:

- `trade_report_intraday`
- `daily_closeout`
- `operator_summary`
- `reporter_analysis`

`Commander` should not own:

- same-day linkage details
- story input shaping
- report generation state semantics
- artifact write ordering
- report markdown/json rendering

Those belong to the reporting owner.

## Reporter-Owned Lanes

### 1. Trade Report Lane

Purpose:

- post-trade lifecycle assembly
- `ai_trade_report`
- operator brief and related trade-level reporting artifacts

Current runtime path:

1. `scripts/run_session.py`
2. `scripts/run_m13_live_loop.py`
3. `graphs/commander_runtime.py`
4. `graphs/nodes/reporter_node.py`
5. `libs/reporting/intraday_trade_reports.py`
6. `scripts/run_live_execution_bundle_report.py`

Target ownership:

- lane owner: `libs/reporting/intraday_trade_reports.py`
- protected core:
  - `libs/reporting/trade_story_pipeline.py`
  - `libs/reporting/trade_report_ai.py`
  - `libs/reporting/llm_artifacts.py`
  - `libs/reporting/trade_bundle_state.py`
  - `libs/reporting/trade_lifecycle_builder.py`
  - `libs/reporting/trade_execution_snapshot.py`

What this means:

- do not add a new owner service layer
- do not move trade-report core again
- keep promoting existing lib ownership
- reduce `scripts/run_live_execution_bundle_report.py` to a thin runtime boundary over time

### 2. Daily / Operator / Analysis Lane

Purpose:

- daily report
- operator summary
- metrics report
- reporter analysis
- optional higher-level operator-facing summaries

Current ownership is mixed:

- `libs/agent/reporter.py`
- `scripts/generate_daily_report.py`
- `scripts/run_operator_daily_summary.py`
- `libs/reporting/operator_visibility.py`
- `libs/reporting/reporter_analysis.py`

Target ownership:

- lane owner: `libs/agent/reporter.py`

What this means:

- `libs/agent/reporter.py` should stop being a script-import facade over time
- it should become the canonical reporting domain entrypoint for:
  - `daily_report`
  - `operator_summary`
  - `metrics_report`
  - `reporter_analysis`
  - optional manual surfaces that still survive pruning

This does not mean everything must collapse into one function.
It means ownership should be clear at the lane boundary.

## Monitoring-Owned Lanes

### 3. Session Monitoring Lane

Purpose:

- `live_watch`
- `live_summary`

These are not the same as trade reports.
They are session telemetry and operator monitoring surfaces.

Target ownership:

- monitoring owner, not Reporter owner

Current ownership:

- `scripts/run_live_session_watch.py`
- `scripts/run_live_session_summary.py`

Current path mismatch:

- `run_session.py` defaults to `reports/live_summary` and `reports/live_watch`
- scripts still default to `reports/dev/live/live_summary` and `reports/dev/live/live_watch`

This lane should be normalized, but it should not be mixed into trade-report ownership.

## Script Boundary Rule

Scripts are allowed to keep only these responsibilities:

- CLI parsing
- lock and process lifecycle
- background loop management
- manual repair entrypoints
- top-level environment/bootstrap concerns

Scripts should not remain owners of:

- report assembly
- story input quality decisions
- same-day linkage policy
- report generation state semantics
- artifact continuity semantics

## Existing Modules To Promote Instead Of Adding New Ones

The current plan is not "add another service".

The current plan is:

- promote existing owners
- remove duplicated orchestration from scripts
- keep core contracts stable

Promotion targets:

- trade lane owner: `libs/reporting/intraday_trade_reports.py`
- daily/operator lane owner: `libs/agent/reporter.py`
- monitoring lane owner: current session-monitoring path, to be normalized separately

Thin-boundary targets:

- `graphs/nodes/reporter_node.py`
- `scripts/run_live_execution_bundle_report.py`
- `scripts/run_ai_trade_report_batch.py`
- `scripts/run_mock_exam_day.py`
- `scripts/run_live_session_watch.py`
- `scripts/run_live_session_summary.py`

## Relation To Other Trade Report Plan Documents

This document must not drift from the other trade-report plan docs.

### Relation to `trade_report_runtime_guardrails_2026-04-16.md`

That document defines:

- protected trade-report contract chain
- files that must not drift
- runtime boundary constraints

This document defines:

- who owns the lane
- who only wraps the lane

### Relation to `report_surface_pruning_2026-04-16.md`

That document defines:

- which `reports/*` roots are kept
- which ones are disabled by default
- which ones are legacy/fallback surfaces

This document defines:

- which owner is responsible for those surfaces

### Relation to `trade_report_external_report_dependencies_2026-04-16.md`

That document defines:

- what the trade report actually consumes

This document defines:

- who owns the lanes that generate those surfaces

## reports/* Lane Summary

This is a summary only.
Detailed pruning rules stay in the pruning document.

### Reporter Domain

- `reports/trades`
- `reports/daily`
- `reports/metrics`
- `reports/dev/analysis/reporter_analysis`

### Monitoring Domain

- `reports/live_summary`
- `reports/live_watch`

### Runtime Truth / Audit / Debug

- `reports/canonical`
- `reports/llm`
- `reports/runtime`
- `reports/dev/*`
- `reports/milestones`

### Legacy / Pruning / Manual-Only Candidates

- `reports/run_cards`
- `reports/decision_story`
- `reports/symbols`
- top-level `reports/operator_summary`
- top-level `reports/trade_explain`

## Completion Phases

### Phase 1. Fix The Ownership Map

Completion criteria:

- `Commander intent`
- `Reporter lane ownership`
- `Monitoring lane ownership`
- `script boundary`

are all explicitly documented and not contradictory.

This document is the completion artifact for Phase 1.

### Phase 2. Finish Trade Report Lane Ownership

Do this without adding a new service layer.

Required direction:

- keep trade-report core where it already is
- move duplicated live/batch orchestration toward existing lib ownership
- reduce `scripts/run_live_execution_bundle_report.py` authority
- keep `graphs/nodes/reporter_node.py` thin

Completion criteria:

- live and batch no longer drift on shared orchestration semantics
- script ownership is reduced
- no new live-only report path appears

### Phase 3. Finish Daily / Operator Lane Ownership

Required direction:

- reduce script-import facade behavior inside `libs/agent/reporter.py`
- let daily/operator/reporter-analysis work converge under one lane owner

Completion criteria:

- daily/operator/reporter-analysis stop behaving like several unrelated script wrappers

### Phase 4. Normalize Monitoring Lane

Required direction:

- normalize `live_summary` / `live_watch` root paths
- stop mixing root and `reports/dev/live/*` defaults

Completion criteria:

- monitoring surfaces use one canonical root policy

### Phase 5. Prune Legacy Surfaces

Only after ownership is clear.

Completion criteria:

- low-value roots are disabled or removed without reappearing through legacy script defaults

## What Must Not Happen

- do not add another reporting owner layer just because ownership is unclear
- do not re-move trade-report core files that were already stabilized
- do not change `reports/trades/*` contracts in the name of cleanup
- do not let `Commander` own report assembly details
- do not force monitoring outputs into Reporter ownership if they are really telemetry

## Success Criteria

The ownership work is successful when all of these are true:

1. `Commander` decides report intents, not report internals
2. trade-report lane clearly belongs to existing Reporter-side lib ownership
3. daily/operator lane clearly belongs to the Reporter domain
4. monitoring lane is explicitly separate from Reporter domain
5. scripts are boundaries, not owners
6. report-surface pruning can happen without ambiguity about who regenerates what

## Final Position

The system does not need "one giant report function".
It needs one owner per lane.

That is the model to align with:

- `Commander` owns intents
- `Reporter` owns reporting lanes
- `Monitoring` owns telemetry lanes
- `scripts` own process boundaries only
