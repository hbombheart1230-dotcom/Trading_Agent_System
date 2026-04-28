# Trade Report Runtime Guardrails (2026-04-16)

## Goal

Reduce script authority under `run_session.py` without regressing the recently stabilized trade report path.

This is not a folder cleanup document.
This is a runtime boundary document.

The first priority is:

1. protect trade report contracts
2. unify live and batch around the same shared service
3. only then thin wrappers / reduce script-to-script execution

## Why This Comes Before Report Surface Cleanup

If report directories are cleaned up first while live and batch still assemble trade reports through different entry paths, the same regressions can return under a different folder layout.

The real risk is not only `reports/*` clutter.
The real risk is runtime drift between:

- live intraday generation
- batch regeneration
- replay / repair flows

## Current Runtime Paths

### Live intraday path

`run_session.py`
-> `run_m13_live_loop.py`
-> `graphs.commander_runtime.run_commander_runtime(...)`
-> `graphs.nodes.reporter_node.reporter_node(...)`
-> `libs.reporting.intraday_trade_reports.generate_intraday_trade_artifacts(...)`
-> `scripts/run_live_execution_bundle_report.py`
-> `libs.reporting.trade_story_pipeline`
-> `libs.reporting.trade_report_ai`

### Batch / repair path

`scripts/run_ai_trade_report_batch.py`
-> read `lifecycle_bundle.json`
-> `build_trade_story_input_from_bundle(...)`
-> default: `build_deterministic_trade_report(...)`
-> optional `--with-llm`: `build_ai_trade_report(...)`
-> `render_trade_report_markdown(...)`
-> sync `report_generation_state.json`

## Protected Contract Chain

These artifacts are the canonical trade report contract chain and must not drift:

1. `reports/trades/<day>/<trade_id>/entry.json`
2. `reports/trades/<day>/<trade_id>/hold.json`
3. `reports/trades/<day>/<trade_id>/exit.json`
4. `reports/trades/<day>/<trade_id>/lifecycle_bundle.json`
5. `reports/trades/<day>/<trade_id>/ai_trade_report_input.json`
6. `reports/trades/<day>/<trade_id>/ai_trade_report_compact_input.json`
7. `reports/trades/<day>/<trade_id>/reports/ai_trade_report.json`
8. `reports/trades/<day>/<trade_id>/reports/ai_trade_report.md`
9. `reports/trades/<day>/<trade_id>/reports/ai_trade_report_llm_response.json`
10. `reports/trades/<day>/<trade_id>/reports/report_generation_state.json`

The runtime refactor is safe only if this chain remains unchanged.

## Files That Must Be Treated As Protected Core

These files are the trade report core and should not be refactored opportunistically while script authority is being reduced:

- `libs/reporting/trade_story_pipeline.py`
- `libs/reporting/trade_report_ai.py`
- `libs/reporting/llm_artifacts.py`
- `libs/reporting/trade_read_model.py`
- `libs/reporting/trade_bundle_state.py`

These files own:

- lifecycle -> story input normalization
- provenance and linkage shaping
- LLM call / salvage / markdown rendering
- artifact path contract
- generation state sync

## Files That Are Safe To Thin, But Not Before Shared-Service Parity

These files are wrappers/orchestrators and are the right targets for authority reduction:

- `scripts/run_session.py`
- `scripts/run_m13_live_loop.py`
- `graphs/nodes/reporter_node.py`
- `libs/reporting/intraday_trade_reports.py`
- `scripts/run_live_execution_bundle_report.py`
- `scripts/run_ai_trade_report_batch.py`
- `scripts/run_mock_exam_day.py`

Important:

- `run_session.py` should remain the official top-level entrypoint.
- `run_live_execution_bundle_report.py` may remain as a CLI/process boundary.
- the goal is not "delete scripts first"
- the goal is "scripts become thin wrappers over one canonical module"

## What Must Not Happen During Refactor

Do not do the following in the first refactor slice:

- change `reports/trades/*` layout
- change `report_generation_state.v1`
- change `build_trade_story_input(...)` input shape
- change `build_ai_trade_report(...)` result contract
- change provenance field names just because wrappers changed
- reintroduce a separate live-only trade report assembly path
- make `single_trade_report.py` the live default path again

## Shared Service Target

The first safe extraction target is a shared service module under `libs/reporting/`.

Recommended candidate:

- `libs/reporting/trade_report_runtime_service.py`

Expected responsibility:

- accept a normalized lifecycle bundle or equivalent runtime inputs
- build / refresh `ai_trade_report_input.json`
- build compact input
- call `build_ai_trade_report(...)`
- render markdown
- persist report artifacts
- sync `report_generation_state.json`
- keep provenance / linkage / diagnostics behavior unchanged

This module should not own:

- process spawning
- lock lifecycle
- CLI parsing
- watch loop logic

## Recommended Refactor Order

### Phase 1. Freeze the contract

Before further runtime refactor, treat the following tests as the minimum contract wall:

- `tests/test_trade_story_pipeline_enrichment.py`
- `tests/test_trade_report_ai.py`
- `tests/test_run_ai_trade_report_batch.py`
- `tests/test_live_execution_bundle_report.py`

Also keep replay validation in scope:

- `scripts/check_trade_report_runtime_regression.py`

### Phase 2. Extract shared trade-report runtime service

First move orchestration code out of:

- `scripts/run_ai_trade_report_batch.py`
- `scripts/run_live_execution_bundle_report.py`

Both should call the same shared service.

This is the key step that protects recent trade report work.

### Phase 3. Switch batch first

Batch is lower risk than live intraday.

Use batch first to prove that:

- story input output is unchanged
- provenance is unchanged
- generation state is unchanged
- markdown section ordering is unchanged

### Phase 4. Switch live bundle to the same service

Only after batch parity is green:

- keep `run_live_execution_bundle_report.py` as a thin process boundary
- move bundle internals to the shared service
- preserve targeted mode, lock handling, and fingerprint behavior

### Phase 5. Reduce script-to-script execution

Only after the live bundle and batch paths already share one service:

- reduce `intraday_trade_reports.py` dependence on direct script ownership
- decide which process boundaries are still truly required
- reduce duplicated CLI wrappers where safe

### Phase 6. Report surface cleanup

Folder cleanup is later.

Only after runtime ownership is canonical should report directories be simplified.

## Concrete "Do First / Do Later"

### Do first

- freeze trade report contract boundaries
- extract one shared runtime service
- move batch and live bundle to that service
- keep wrappers thin

### Do later

- reduce `reports/*` surface
- remove legacy report roots
- simplify operator-facing report inventory

## Why `run_live_execution_bundle_report.py` Cannot Be Yanked Out Blindly

Even after recent lib extraction (`trade_lifecycle_builder`, `trade_execution_snapshot`, `trade_bundle_state`), this script still owns important orchestration concerns:

- targeted run filtering
- lifecycle assembly coordination
- same-day reporter linkage usage
- artifact write ordering
- fingerprint/idempotency behavior
- bundle summary emission for live caller expectations

So the next step is not "remove the script".
The next step is "empty the script safely".

## Safe Success Criteria

The refactor is successful only if all of the following remain true:

- live and batch produce the same `ai_trade_report_input.json` for the same lifecycle
- provenance and linkage fields do not regress to blanket fallback
- `report_generation_state.json` remains component-compatible
- `ai_trade_report.md` section order and content quality do not regress
- runtime regression harness still passes on representative real trades

## Practical Decision

Trade report stabilization work is not blocked by reducing script authority.
But script authority must be reduced in a way that preserves trade report parity first.

Therefore:

1. do not start with folder cleanup
2. do not start with UI cleanup
3. start with shared-service extraction under the existing trade report contract
