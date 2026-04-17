# Live Bundle Lib Extraction Draft (2026-04-16)

## Goal

Reduce `scripts/run_live_execution_bundle_report.py` until live reporting no longer needs it.

This is a live-path reduction document.
It does not redesign trade-report core.

## Current Position

Live trade-report core is already mostly in libs.

Protected core already outside the script:

- `libs/reporting/trade_story_pipeline.py`
- `libs/reporting/trade_report_ai.py`
- `libs/reporting/llm_artifacts.py`
- `libs/reporting/trade_bundle_state.py`
- `libs/reporting/trade_lifecycle_builder.py`
- `libs/reporting/trade_execution_snapshot.py`

The remaining problem is not "bundle still owns trade-report core".
The remaining problem is "live runtime orchestration is still split between lib and script".

## What Has Already Been Extracted

### Module 1: `libs/reporting/trade_lifecycle_builder.py`

Current responsibility:

- run snapshots -> lifecycle assemble
- BUY/SELL/holding attach rules
- same-symbol attach fallback
- lifecycle recovery metadata
- lifecycle attach debug payload

### Module 2: `libs/reporting/trade_execution_snapshot.py`

Current responsibility:

- execution payload normalize
- run-level execution snapshot
- execution detail merge/fallback
- order/filled/qty/status source merge

### Module 3: `libs/reporting/trade_bundle_persistence.py`

Current responsibility:

- final trade artifact write ordering
- artifact presence recomputation
- `_health.json` finalization
- `_artifact_links.json` persistence

Related helper module that remains separate:

- `libs/reporting/trade_bundle_state.py`
  - generation-state component builders
  - health/provenance helpers
  - fingerprint helpers

### Module 4: `libs/reporting/trade_bundle_assembly.py`

Current responsibility:

- canonical source resolution / preferred run-id ordering
- live run-bundle payload shaping
  - aggregated execution bundle base payload
  - story contract / human-readable sections
  - run-level timeline / warnings / operator conclusion
- canonical artifact preference / run-level hydration
  - canonical payload preference
  - merged execution snapshot for run bundle
  - evidence_provenance / canonical path attachment
- entry/exit execution-detail attachment
- holding-phase observability attachment
- same-day reporter linkage attachment
- strategy-anchor linkage attachment
- strategy-anchor metadata attachment
- entry/exit/holding context enrichment
- fallback holding-event synthesis
- strategist/scanner trace-summary mirroring
- selected-symbol / runner-up / candidate-count attachment
- lifecycle / lifecycle_bundle summary-field updates

This is the first extracted slice of live bundle assembly.
The full bundle assembly is not fully moved yet.

### Shared Orchestration Helpers Now Under `libs/reporting/intraday_trade_reports.py`

Current responsibility:

- trade-id filter normalization
- story-input regeneration from lifecycle bundle
- story-input persist strategy / compact-input artifact persistence
- report-generation-state path/load/write
- ai-report diagnostics sync/finalize helpers
- runtime diagnostics context shaping
- live generation-state payload shaping
- lifecycle-row / run-bundle backfill payload shaping
- run-bundle row patch apply / bundle rewrite
- final live-execution summary payload shaping
- live report-generation planning
  - fingerprint-match reuse decision
  - existing-report reuse when AI generation is disabled
  - deterministic-only fallback decision
- AI generation result normalization
  - LLM result -> diagnostics mapping
  - failed generation -> deterministic preservation mapping
- AI generation execution wrapper
  - live script now hands the actual builder call to shared intraday helper
- trade-report policy resolution / diagnostics gate seeding
  - open-trade generation gate now reuses shared intraday helper
  - report reason / next-step / base diagnostics mapping now reuses shared intraday helper
- final diagnostics / artifacts / path mutation
  - lifecycle, lifecycle_bundle, story_input, trade_report mutation now reuse shared assembly helper
- final state payload assembly
  - lifecycle_bundle_v1, provenance, health, artifact-links payloads now reuse shared trade-bundle-state helper
- owner entrypoint remains here, but internal helper clusters are now split again:
  - `libs/reporting/trade_report_runtime_policy.py`
    - policy resolution
    - base diagnostics
    - reason/next-step mapping
  - `libs/reporting/trade_report_runtime_generation.py`
    - generation-state IO
    - runtime diagnostics shaping
    - AI generation planning/result application/execution

## What The Live Script Still Owns

The live script still owns three different kinds of responsibility.

### 1. Process Boundary / Runtime Control

These are valid script-side responsibilities for now:

- background lock and heartbeat
- stale lock / stale process cleanup
- background queue management
- sync vs background execution split
- CLI parsing
- top-level report summary emission

Note:

- sync live path no longer needs the full script boundary
- `generate_intraday_trade_artifacts()` now uses an in-process runner for sync execution
- background live path no longer launches the script file directly
- background live path now launches `python -m libs.reporting.live_execution_bundle_runner`
- script boundary remains as manual/repair CLI and compatibility wrapper

These can remain script-side until the end.

### 2. Live Bundle Assembly

Still script-owned today:

- trade-level compatibility bridge fields that are still applied inline

This is the main live-only orchestration block still preventing full script removal.

### 3. Live-Specific Generation Flow

Still script-owned today:

- final story-input / bundle mutation glue around already-built payloads

This is the second major blocker.

## What Has Been Partially Reduced Already

The following script-side responsibilities have already started moving toward shared lib ownership:

- lifecycle building now delegates to `trade_lifecycle_builder`
- execution snapshot now delegates to `trade_execution_snapshot`
- fingerprint helpers now delegate to `trade_bundle_state`
- report-generation-state IO now reuses `intraday_trade_reports`
- fingerprint reuse / deterministic fallback planning now reuse `intraday_trade_reports`
- AI generation result -> diagnostics mapping now reuses `intraday_trade_reports`
- actual AI generation execution now reuses `intraday_trade_reports`
- strategist / AI LLM response artifact persistence now reuses `trade_bundle_persistence`
- trade report json/md write + refresh flow now reuses `trade_bundle_persistence`
- final diagnostics / artifacts / path mutation now reuses `trade_bundle_assembly`
- final lifecycle/provenance/health/link payload assembly now reuses `trade_bundle_state`
- story-input persist strategy and compact-input artifact write now reuse `intraday_trade_reports`
- run-bundle row patch apply and bundle rewrite now reuse `intraday_trade_reports`
- trade-report policy resolution and diagnostics gate seeding now reuse `intraday_trade_reports`
- run-level bundle payload shaping now reuses `trade_bundle_assembly`
- canonical artifact preference and run-level hydration now reuse `trade_bundle_assembly`
- batch path now reuses shared `intraday_trade_reports` helpers for:
  - trade-id filter normalization
  - story-input regeneration
  - diagnostics sync/finalize
  - generation-state sync

This means the next live reduction slice should continue from shared orchestration, not invent another service.

## Remaining Responsibilities Before Live Can Drop The Script

Live can stop calling `run_live_execution_bundle_report.py` only after these are absorbed into existing lib ownership.

### A. Same-Day Linkage And Trade-Level Live Bundle Assembly

Must move out of the script:

- `_resolve_lifecycle_bundle_sources(...)`
- `_build_same_day_reporter_linkage(...)`
- holding-phase observability merge into the final trade bundle
- selected-symbol / candidate-count / trace-summary attachment

Target owner:

- existing Reporter-side lib ownership
- practically: `libs/reporting/intraday_trade_reports.py` plus protected core helpers

### B. Trade Artifact Persistence Bundle

Must move out of the script:

- final write ordering for lifecycle + health + provenance + artifact links
- post-write artifact presence refresh

Target owner:

- existing persistence helpers around `trade_bundle_state`
- no new service layer required

### C. Live Generation-State And Diagnostics Orchestration

Must move out of the script:

- richer live `generation_state` shaping
- shared diagnostics enrichment
- final propagation of `ai_report_diagnostics`
- report policy resolution for live path

Target owner:

- existing shared helpers first
- then any remaining glue should live in `intraday_trade_reports.py`

## What Must Stay Script-Side Even After Live Removal

Even if live stops using the script as the primary path, these responsibilities may remain in a CLI wrapper:

- manual repair / replay entrypoint
- offline batch regeneration entrypoint
- explicit process boundary for operator use
- lock and long-running background control if still needed operationally

This means "remove from live" does not automatically mean "delete the file immediately".

## Safe Removal Order

### Phase 1. Finish Shared Orchestration Reuse

Keep reducing duplicated logic by reusing existing helpers from:

- `trade_lifecycle_builder`
- `trade_execution_snapshot`
- `trade_bundle_state`
- `intraday_trade_reports`

Completion criteria:

- no new helper duplication appears in live vs batch

### Phase 2. Absorb Live Bundle Assembly Into Existing Lib Ownership

Move:

- same-day linkage
- holding observability attachment
- strategy-anchor linkage
- trace-summary / selected-symbol / candidate-count shaping
- final trade-bundle shaping

Completion criteria:

- `intraday_trade_reports.py` can assemble a trade-level bundle without shelling out to the script

### Phase 3. Absorb Final Trade Artifact Persistence

Move:

- lifecycle/provenance/health/links write ordering
- post-write artifact presence refresh
- summary row backfill

Completion criteria:

- in-process live path can produce full trade artifacts safely

### Phase 4. Switch Live Path To In-Process Only

Target path:

`run_session.py`
-> `run_m13_live_loop.py`
-> `graphs/commander_runtime.py`
-> `graphs/nodes/reporter_node.py`
-> `libs/reporting/intraday_trade_reports.py`
-> protected core libs
-> done

At this point:

- live no longer needs `run_live_execution_bundle_report.py`
- bundle script can be reduced to manual repair/batch CLI only

### Phase 5. Decide Whether The Script Still Has Value

Only after live is fully off the script:

- keep as repair-only CLI
- or delete if repair/replay no longer needs a separate process boundary

## Invariants During Removal

- `reports/trades/*` structure unchanged
- lifecycle linkage behavior unchanged
- `report_generation_state.v1` unchanged
- no live-only alternate trade-report contract appears
- regression harness stays green

## Final Position

Live script removal is possible.
It is not the first step.

Current position:

- sync live path is effectively boundaryless
- background/manual path still uses `run_live_execution_bundle_report.py`

The correct order is:

1. remove remaining live-only orchestration from the script
2. switch live to in-process lib ownership
3. demote the script to manual repair
4. only then decide whether to delete it
