# Phase 9.3 Large Reporting Hotspot Map

Date: 2026-05-17

## Scope

Phase 9.3 covers the largest reporting hotspots. The goal is modularity and extension safety, not behavior changes.

Current target sizes before the first extraction:

- `libs/reporting/trade_report_ai.py`: 10267 lines
- `libs/reporting/trade_report_markdown_clean.py`: 6494 lines
- `libs/reporting/trade_story_pipeline.py`: 4874 lines

## Responsibility Map

`trade_report_ai.py`

- LLM execution profile and router call handling
- Shared trade fact precedence and deterministic report seed
- Compact LLM input construction
- AI/fallback merge and language normalization
- Trade report and trade summary LLM message construction
- Public adapter functions for markdown rendering and summary generation

`trade_report_markdown_clean.py`

- Full markdown and summary markdown rendering
- Trade summary input surface
- Symbol name/theme metadata resolution
- Cost, PnL, price truth, and post-exit shadow sections
- Memory, strategy, scanner, monitor, and truth-surface markdown sections
- Korean operator-facing label normalization

`trade_story_pipeline.py`

- Lifecycle bundle loading and story input assembly
- Evidence hydration and provenance repair
- Market, scanner, filter, monitor, guard, execution, reporter, and operator human payload assembly
- Timeline, warnings, and story markdown summary support

## Coarse Module Boundaries

Implemented first:

- `libs/reporting/trade_report_common.py`
  - Shared clipping, safe numeric conversion, list compaction, scalar compaction, placeholder checks, percent/price formatting.
  - Used by `trade_report_ai.py` and `trade_story_pipeline.py` without changing their public helper names.
- `libs/reporting/trade_report_ai_shared_facts.py`
  - Trade fact precedence resolver for lifecycle action/status, holding duration, exit reason, broker/API PnL, price/PnL truth metadata, and monitor decision facts.
  - `trade_report_ai.py` keeps a thin `_resolve_trade_facts_with_precedence` wrapper and passes local dependencies as callbacks to avoid circular imports.
- `libs/reporting/trade_report_ai_compact_input.py`
  - Sparse LLM payload construction for reporter prompts.
  - `trade_report_ai.py` keeps wrapper surfaces and passes deeper compact-story/timeline/reporter-placeholder dependencies as callbacks.
- `libs/reporting/trade_report_ai_compact_helpers.py`
  - Shared compact helper logic used by report AI input preparation and section construction.
  - Covers event row, timeline row, tail list, and monitor snapshot compaction.
- `libs/reporting/trade_report_ai_merge_policy.py`
  - AI/fallback text, summary, bullet, and section merge policy.
  - Keeps language/noise classifiers as callbacks to avoid coupling back into the large report AI module.
- `libs/reporting/trade_report_symbol_metadata.py`
  - Symbol name and symbol-specific theme metadata resolution for trade markdown and summary rendering.
  - Keeps markdown renderer translation/metadata formatting as callbacks.
- `libs/reporting/trade_report_post_exit_shadow.py`
  - Post-exit shadow surface, checkpoint compaction, label mapping, and observation-only markdown lines.
  - Keeps markdown money/percent/status formatting as callbacks.
- `libs/reporting/trade_story_evidence.py`
  - Story-pipeline evidence helpers for substantive exit evidence, placeholder replacement, and evidence provenance derivation.

Next broad boundaries:

- `libs/reporting/trade_report_ai/shared_facts.py`
  - Move shared summary seed construction after its remaining dependencies are isolated.
- `libs/reporting/trade_report_ai/compact_input.py`
  - Move the remaining deep compact story input builder, strategist context digest helpers, and evidence digest helpers.
- `libs/reporting/trade_report_ai/fallback_merge.py`
  - Move deterministic fallback sections and candidate/failure report construction after their shared section dependencies are isolated.
- `libs/reporting/trade_report_ai/prompting.py`
  - Move report and summary message builders.
- `libs/reporting/trade_report_markdown/symbol_metadata.py`
  - Done as `libs/reporting/trade_report_symbol_metadata.py`.
- `libs/reporting/trade_report_markdown/post_exit_shadow.py`
  - Done as `libs/reporting/trade_report_post_exit_shadow.py`.
- `libs/reporting/trade_report_markdown/truth_sections.py`
  - Move cost, PnL, price, memory, and truth-surface section builders.
- `libs/reporting/trade_story/evidence.py`
  - Started as `libs/reporting/trade_story_evidence.py`; larger evidence hydration can be split later.
- `libs/reporting/trade_story/human_sections.py`
  - Move market/scanner/monitor/execution human payload builders.

## First Patch Result

- Added `libs/reporting/trade_report_common.py`.
- Removed duplicated common utility definitions from:
  - `libs/reporting/trade_report_ai.py`
  - `libs/reporting/trade_story_pipeline.py`
- Preserved existing call names through import aliases:
  - `_clip`, `_listify`, `_fmt_pct`, `_fmt_price`, etc. in AI report code.
  - `clip`, `safe_int`, `safe_float`, `_list_text`, etc. in story pipeline code.

Resulting sizes after the first extraction:

- `libs/reporting/trade_report_ai.py`: 10183 lines
- `libs/reporting/trade_story_pipeline.py`: 4801 lines
- `libs/reporting/trade_report_common.py`: 174 lines

## Second Patch Result

- Added `libs/reporting/trade_report_ai_shared_facts.py`.
- Moved `_resolve_trade_facts_with_precedence` implementation out of `trade_report_ai.py`.
- Preserved existing `trade_report_ai._resolve_trade_facts_with_precedence(story_input)` test and internal call surface through a wrapper.

Resulting sizes after the second extraction:

- `libs/reporting/trade_report_ai.py`: 9807 lines
- `libs/reporting/trade_report_ai_shared_facts.py`: 471 lines

## Third Patch Result

- Added `libs/reporting/trade_report_ai_compact_input.py`.
- Moved sparse LLM payload construction out of `trade_report_ai.py`.
- Preserved existing wrapper names:
  - `build_ai_trade_report_compact_input`
  - `_compact_section_seed_for_llm`
  - `_sparse_story_input_for_llm`

Resulting sizes after the third extraction:

- `libs/reporting/trade_report_ai.py`: 9488 lines
- `libs/reporting/trade_report_ai_compact_input.py`: 355 lines

## Fourth Patch Result

- Added `libs/reporting/trade_report_ai_compact_helpers.py`.
- Moved reusable compact helpers out of `trade_report_ai.py`.
- Preserved existing wrapper names:
  - `_tail_list`
  - `_compact_event_row`
  - `_compact_timeline_rows`
  - `_compact_monitor_snapshot`

Resulting sizes after the fourth extraction:

- `libs/reporting/trade_report_ai.py`: 9345 lines
- `libs/reporting/trade_report_ai_compact_helpers.py`: 175 lines

## Fifth Patch Result

- Added `libs/reporting/trade_report_ai_merge_policy.py`.
- Moved AI/fallback merge policy helpers out of `trade_report_ai.py`.
- Preserved existing wrapper names for tests and internal callers.

Resulting sizes after the fifth extraction:

- `libs/reporting/trade_report_ai.py`: 9056 lines
- `libs/reporting/trade_report_ai_merge_policy.py`: 369 lines

## Sixth Patch Result

- Added `libs/reporting/trade_report_symbol_metadata.py`.
- Moved symbol name/theme metadata resolution out of `trade_report_markdown_clean.py`.
- Preserved existing wrapper names in the markdown renderer.

Resulting sizes after the sixth extraction:

- `libs/reporting/trade_report_markdown_clean.py`: 6334 lines
- `libs/reporting/trade_report_symbol_metadata.py`: 283 lines

## Seventh Patch Result

- Added `libs/reporting/trade_report_post_exit_shadow.py`.
- Moved post-exit shadow observation rendering support out of `trade_report_markdown_clean.py`.
- Preserved existing wrapper names in the markdown renderer.

Resulting sizes after the seventh extraction:

- `libs/reporting/trade_report_markdown_clean.py`: 6217 lines
- `libs/reporting/trade_report_post_exit_shadow.py`: 157 lines

## Eighth Patch Result

- Added `libs/reporting/trade_story_evidence.py`.
- Moved story-pipeline evidence/provenance helpers out of `trade_story_pipeline.py`.
- Preserved existing wrapper names in the story pipeline.

Resulting sizes after the eighth extraction:

- `libs/reporting/trade_story_pipeline.py`: 4747 lines
- `libs/reporting/trade_story_evidence.py`: 76 lines

## Regression Matrix

Passed:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_common.py libs\reporting\trade_report_ai.py libs\reporting\trade_story_pipeline.py libs\reporting\trade_report_markdown_clean.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_reporting_provenance_preference.py tests\test_phase3_lifecycle_bundle.py -q --basetemp .pytest-work-phase93-story`
  - 44 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase93-ai`
  - 134 passed
- `venv\Scripts\python.exe -m pytest tests\test_intraday_trade_reports.py tests\test_symbol_trade_report.py tests\test_trade_explain_report.py -q --basetemp .pytest-work-phase93-render`
  - 40 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_memory_surface.py tests\test_trade_memory_application_surface.py tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase93-memory`
  - 76 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py -q --basetemp .pytest-work-phase93-shared-final`
  - 131 passed
- Additional Slice 2 focused sets passed:
  - shared AI facts: 128 passed
  - metadata/index context: 6 passed
  - story/provenance: 39 passed
  - render: 40 passed
  - memory/live bundle: 76 passed
  - batch/separated adapter: 20 passed
- Slice 3 compact input focused sets passed:
  - AI report: 128 passed
  - metadata/index context: 6 passed
  - batch/separated adapter: 20 passed
  - render: 40 passed
  - story/provenance: 39 passed
  - memory/live bundle: 76 passed
- Slice 4 compact helper focused sets passed:
  - AI report: 128 passed
  - story/provenance: 39 passed
  - batch/separated adapter: 20 passed
  - render: 40 passed
  - memory/live bundle: 76 passed
  - metadata/index context: 6 passed
- Slice 5 merge policy focused sets passed:
  - AI report: 128 passed
  - batch/separated adapter: 20 passed
  - render: 40 passed
  - story/provenance/metadata/index context: 45 passed
  - memory/live bundle: 76 passed
- Slice 6 symbol metadata focused sets passed:
  - summary/render: 43 passed
  - AI report: 128 passed
  - batch/separated adapter: 20 passed
  - story/provenance/index context: 42 passed
  - memory/live bundle: 76 passed
- Slice 7 post-exit shadow focused sets passed:
  - summary/render: 43 passed
  - AI report: 128 passed
  - batch/separated adapter: 20 passed
  - story/provenance/index context: 42 passed
  - memory/live bundle: 76 passed
- Slice 8 story evidence focused sets passed:
  - story/provenance: 39 passed
  - AI report/metadata/index context: 134 passed
  - batch/separated adapter: 20 passed
  - memory/live bundle: 76 passed
  - render: 40 passed

Known unrelated failure in broader single-report batch:

- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_single_trade_report.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase93-batch`
  - 26 passed, 1 failed
  - Failure: `tests/test_single_trade_report.py::test_commander_runtime_restores_intraday_bundle_helper_for_live_reports`
  - Cause observed: existing `graphs/commander_runtime.py` refactor removed the literal source import string expected by the test. It is outside this Phase 9.3 reporting utility extraction.

## Live Restart

No live restart was performed. The market is closed and the user explicitly said restart is not needed.

## Phase 9.3 Closeout

Status: closed.

Phase 9.3 is closed after eight broad, behavior-preserving extraction slices. The goal was not to finish every possible large-file split, but to establish stable module boundaries around the highest-risk reporting hotspots without changing live trading behavior.

Completed boundaries:

- common reporting utilities
- AI trade fact precedence
- AI sparse compact input
- AI compact helper utilities
- AI/fallback merge policy
- trade summary symbol metadata
- post-exit shadow rendering
- story evidence/provenance helpers

Deferred boundaries:

- remaining AI prompt builders
- deterministic fallback report construction
- markdown truth/cost/PnL section builders
- larger story evidence hydration and human-section builders

Those deferred areas should be handled only after Phase 10 broad regression confirms the current extraction base is stable.

Live restart remains intentionally skipped because the market is closed and the current workstream is reporting modularization, not a requested live runtime change.

## Phase 10 Broad Regression Closeout

Phase 10 completed as a closeout verification pass for the Phase 9.3 reporting modularization base.

Passed:

- reporting module syntax checks
- AI trade report tests
- trade summary symbol metadata tests
- Korea market index context tests
- AI trade report batch adapter tests
- separated adapter tests
- intraday/symbol/explain markdown render tests
- story pipeline enrichment tests
- reporting provenance preference tests
- trade memory surface tests
- trade memory application surface tests
- live execution bundle report tests
- diff whitespace check for the Phase 9.3 reporting/doc files

Known unrelated failure reproduced:

- `tests/test_single_trade_report.py::test_commander_runtime_restores_intraday_bundle_helper_for_live_reports`
- The test asserts that `graphs/commander_runtime.py` still contains the literal import string `from graphs.nodes.reporter_node import reporter_node`.
- The failure is unchanged from Phase 9.3 and belongs to the commander runtime import-boundary refactor, not the reporting extraction work.

Phase 10 did not perform a live restart because the market is closed and no restart was requested for this verification-only pass.
