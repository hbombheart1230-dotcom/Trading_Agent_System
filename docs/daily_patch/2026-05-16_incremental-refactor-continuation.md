# 2026-05-16 Incremental Refactor Continuation

## Phase 10 - Broad Regression and Reporting Refactor Closeout

- Closed Phase 9.3 after eight broad reporting extraction slices.
- Phase 10 scope is verification and documentation, not another behavior change.
- Broad regression focus:
  - syntax checks for the reporting modules added or touched in Phase 9.3
  - trade report AI tests
  - trade summary symbol metadata tests
  - market index context tests
  - batch AI report adapter tests
  - markdown render tests
  - story/provenance tests
  - memory/live bundle report tests
- Live restart policy:
  - no restart for this closeout pass because the market is closed and the user explicitly did not need a restart.
  - if these modules are changed during live market hours later, restart policy should be evaluated at that time.

### Phase 9.3 Closeout Result

- Completed extraction modules:
  - `libs/reporting/trade_report_common.py`
  - `libs/reporting/trade_report_ai_shared_facts.py`
  - `libs/reporting/trade_report_ai_compact_input.py`
  - `libs/reporting/trade_report_ai_compact_helpers.py`
  - `libs/reporting/trade_report_ai_merge_policy.py`
  - `libs/reporting/trade_report_symbol_metadata.py`
  - `libs/reporting/trade_report_post_exit_shadow.py`
  - `libs/reporting/trade_story_evidence.py`
- Deferred to later phases:
  - remaining AI prompt/fallback report builders
  - markdown truth/cost/PnL sections
  - larger story evidence hydration and human-section builders
- Known unrelated issue still tracked separately:
  - `tests/test_single_trade_report.py::test_commander_runtime_restores_intraday_bundle_helper_for_live_reports`
  - observed cause: commander runtime import-boundary expectation from a previous refactor, outside the Phase 9.3 reporting extraction.

### Phase 10 Verification Result

- Passed:
  - `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_markdown_clean.py libs\reporting\trade_story_pipeline.py libs\reporting\trade_report_common.py libs\reporting\trade_report_ai_shared_facts.py libs\reporting\trade_report_ai_compact_input.py libs\reporting\trade_report_ai_compact_helpers.py libs\reporting\trade_report_ai_merge_policy.py libs\reporting\trade_report_symbol_metadata.py libs\reporting\trade_report_post_exit_shadow.py libs\reporting\trade_story_evidence.py`
  - `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase10-ai`
    - 134 passed
  - `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase10-batch`
    - 20 passed
  - `venv\Scripts\python.exe -m pytest tests\test_intraday_trade_reports.py tests\test_symbol_trade_report.py tests\test_trade_explain_report.py -q --basetemp .pytest-work-phase10-render`
    - 40 passed
  - `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_reporting_provenance_preference.py -q --basetemp .pytest-work-phase10-story`
    - 39 passed
  - `venv\Scripts\python.exe -m pytest tests\test_trade_memory_surface.py tests\test_trade_memory_application_surface.py tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase10-memory`
    - 76 passed
  - `git diff --check` for Phase 9.3 reporting/doc files
- Known unrelated failure reproduced:
  - `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_single_trade_report.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase10-single-batch`
    - 26 passed, 1 failed
  - Failure: `tests/test_single_trade_report.py::test_commander_runtime_restores_intraday_bundle_helper_for_live_reports`
  - Assertion: test still expects the literal source string `from graphs.nodes.reporter_node import reporter_node` in `graphs/commander_runtime.py`.
  - Assessment: unchanged from Phase 9.3 and outside the reporting modularization surface.
- Live restart: not performed.

## Phase 9.3 Slice 1 - Large Reporting Common Utility Boundary

- Added `libs/reporting/trade_report_common.py`.
- Extracted duplicated common helpers from `libs/reporting/trade_report_ai.py` and `libs/reporting/trade_story_pipeline.py`.
- Preserved existing call names through import aliases to avoid behavior changes.
- Added `docs/dev/phase_9_3_large_reporting_hotspot_map_2026-05-17.md`.
- Verification passed: py_compile, 44 story tests, 134 AI/report tests, 40 render tests, 76 memory/live bundle tests.
- Known unrelated failure: `tests/test_single_trade_report.py::test_commander_runtime_restores_intraday_bundle_helper_for_live_reports` expects a literal `graphs.nodes.reporter_node` import string removed by the existing commander runtime refactor.
- Result sizes: `trade_report_ai.py` 10183 lines, `trade_story_pipeline.py` 4801 lines, `trade_report_common.py` 174 lines.
- Live restart: not performed.

## Phase 9.3 Slice 2 - Trade Report AI Shared Facts Boundary

- Added `libs/reporting/trade_report_ai_shared_facts.py`.
- Moved the trade fact precedence resolver out of `libs/reporting/trade_report_ai.py`.
- Kept the existing `_resolve_trade_facts_with_precedence(story_input)` call surface in `trade_report_ai.py` as a thin wrapper.
- Passed still-local dependencies as callbacks:
  - `_load_trade_read_model_hint`
  - `_humanize_duration_text`
  - `_actual_lifecycle_action`
- This keeps the new module focused on broker/API PnL, monitor/lifecycle/action/status, and exit reason precedence without creating circular imports.

### Verification

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_ai_shared_facts.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase93-shared-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase93-shared-meta`
  - 6 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_reporting_provenance_preference.py -q --basetemp .pytest-work-phase93-shared-story`
  - 39 passed
- `venv\Scripts\python.exe -m pytest tests\test_intraday_trade_reports.py tests\test_symbol_trade_report.py tests\test_trade_explain_report.py -q --basetemp .pytest-work-phase93-shared-render`
  - 40 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_memory_surface.py tests\test_trade_memory_application_surface.py tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase93-shared-memory`
  - 76 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase93-shared-batch`
  - 20 passed
- Final focused check:
  - `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py -q --basetemp .pytest-work-phase93-shared-final`
  - 131 passed

### Result

- `libs/reporting/trade_report_ai.py`: 9807 lines
- `libs/reporting/trade_report_ai_shared_facts.py`: 471 lines
- Live restart: not performed.

## Phase 9.3 Slice 3 - Trade Report AI Sparse Compact Input Boundary

- Added `libs/reporting/trade_report_ai_compact_input.py`.
- Moved sparse LLM payload construction out of `libs/reporting/trade_report_ai.py`.
- Kept existing public/internal call surfaces in `trade_report_ai.py`:
  - `build_ai_trade_report_compact_input`
  - `_compact_section_seed_for_llm`
  - `_sparse_story_input_for_llm`
- Passed still-local dependencies as callbacks:
  - `_compact_story_input_for_llm`
  - `_reporter_summary_is_placeholder`
  - `_compact_timeline_rows`
- This isolates the token-facing sparse prompt payload shape while leaving deeper evidence/context compaction for a later boundary.

### Verification

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_ai_compact_input.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase93-compact-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase93-compact-meta`
  - 6 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase93-compact-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_intraday_trade_reports.py tests\test_symbol_trade_report.py tests\test_trade_explain_report.py -q --basetemp .pytest-work-phase93-compact-render`
  - 40 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_reporting_provenance_preference.py -q --basetemp .pytest-work-phase93-compact-story`
  - 39 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_memory_surface.py tests\test_trade_memory_application_surface.py tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase93-compact-memory`
  - 76 passed

### Result

- `libs/reporting/trade_report_ai.py`: 9488 lines
- `libs/reporting/trade_report_ai_compact_input.py`: 355 lines
- Live restart: not performed.

## Phase 9.3 Slice 4 - Trade Report AI Compact Helper Boundary

- Added `libs/reporting/trade_report_ai_compact_helpers.py`.
- Moved reusable compact helper logic out of `libs/reporting/trade_report_ai.py`:
  - tail list compaction
  - event row compaction
  - timeline row compaction
  - monitor snapshot compaction
- Kept existing wrapper names in `trade_report_ai.py`:
  - `_tail_list`
  - `_compact_event_row`
  - `_compact_timeline_rows`
  - `_compact_monitor_snapshot`
- Passed `_compact_entry_candidate_cascade` as a callback to avoid moving a wider entry-control dependency set in this slice.

### Verification

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_ai_compact_helpers.py libs\reporting\trade_report_ai_compact_input.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase93-helpers-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_reporting_provenance_preference.py -q --basetemp .pytest-work-phase93-helpers-story`
  - 39 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase93-helpers-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_intraday_trade_reports.py tests\test_symbol_trade_report.py tests\test_trade_explain_report.py -q --basetemp .pytest-work-phase93-helpers-render`
  - 40 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_memory_surface.py tests\test_trade_memory_application_surface.py tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase93-helpers-memory`
  - 76 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase93-helpers-meta`
  - 6 passed

### Result

- `libs/reporting/trade_report_ai.py`: 9345 lines
- `libs/reporting/trade_report_ai_compact_helpers.py`: 175 lines
- Live restart: not performed.

## Phase 9.3 Slice 5 - Trade Report AI Merge Policy Boundary

- Added `libs/reporting/trade_report_ai_merge_policy.py`.
- Moved AI/fallback merge policy helpers out of `libs/reporting/trade_report_ai.py`:
  - fallback text preference
  - scanner/execution mismatch detection
  - scanner selection label detection
  - fallback summary preference
  - priority bullet prefix policy
  - bullet merge policy
  - section merge policy
- Kept existing wrapper names in `trade_report_ai.py`:
  - `_prefer_fallback_text`
  - `_is_scanner_execution_mismatch_text`
  - `_is_scanner_selection_label_line`
  - `_prefer_fallback_summary`
  - `_trade_report_priority_bullet_prefixes`
  - `_merge_bullets_with_fallback`
  - `_merge_section_with_fallback`
- Passed report-language/noise helpers as callbacks so the merge module stays independent of the larger AI report file.
- Left `_merge_trade_report_candidate`, `_fallback_report`, `_failure_report`, and parse metadata in `trade_report_ai.py` for now because they still depend on broad report construction context.

### Verification

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_ai_merge_policy.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase93-merge-ai2`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase93-merge-batch2`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_intraday_trade_reports.py tests\test_symbol_trade_report.py tests\test_trade_explain_report.py -q --basetemp .pytest-work-phase93-merge-render2`
  - 40 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_reporting_provenance_preference.py tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase93-merge-story2`
  - 45 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_memory_surface.py tests\test_trade_memory_application_surface.py tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase93-merge-memory2`
  - 76 passed

### Result

- `libs/reporting/trade_report_ai.py`: 9056 lines
- `libs/reporting/trade_report_ai_merge_policy.py`: 369 lines
- Live restart: not performed.

## Phase 9.3 Slice 6 - Trade Report Markdown Symbol Metadata Boundary

- Added `libs/reporting/trade_report_symbol_metadata.py`.
- Moved symbol name/theme metadata resolution out of `libs/reporting/trade_report_markdown_clean.py`.
- Kept existing wrapper names in `trade_report_markdown_clean.py`:
  - `_append_unique_text`
  - `_append_theme_values`
  - `_iter_trade_symbol_metadata_sources`
  - `_symbol_in_theme_components`
  - `_iter_nested_dicts`
  - `_component_themes_for_symbol`
  - `_infer_symbol_name_from_report_text`
  - `_resolve_trade_symbol_metadata`
- Passed `_metadata_value` and `_translate_text` as callbacks to avoid coupling the metadata module to the full markdown renderer.

### Verification

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_markdown_clean.py libs\reporting\trade_report_symbol_metadata.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_intraday_trade_reports.py tests\test_symbol_trade_report.py tests\test_trade_explain_report.py -q --basetemp .pytest-work-phase93-symbol-render`
  - 43 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase93-symbol-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase93-symbol-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_reporting_provenance_preference.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase93-symbol-story`
  - 42 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_memory_surface.py tests\test_trade_memory_application_surface.py tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase93-symbol-memory`
  - 76 passed

### Result

- `libs/reporting/trade_report_markdown_clean.py`: 6334 lines
- `libs/reporting/trade_report_symbol_metadata.py`: 283 lines
- Live restart: not performed.

## Phase 9.3 Slice 7 - Trade Report Markdown Post-Exit Shadow Boundary

- Added `libs/reporting/trade_report_post_exit_shadow.py`.
- Moved post-exit shadow observation rendering support out of `libs/reporting/trade_report_markdown_clean.py`.
- Kept existing wrapper names in `trade_report_markdown_clean.py`:
  - `_post_exit_shadow_surface`
  - `_checkpoint_label`
  - `_compact_post_exit_shadow`
  - `_build_post_exit_shadow_summary_lines`
- Passed markdown formatting helpers as callbacks:
  - `_summary_money`
  - `_fmt_pct`
  - `_metadata_value`
  - `_num_opt`

### Verification

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_markdown_clean.py libs\reporting\trade_report_post_exit_shadow.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_intraday_trade_reports.py tests\test_symbol_trade_report.py tests\test_trade_explain_report.py -q --basetemp .pytest-work-phase93-postexit-render`
  - 43 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase93-postexit-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase93-postexit-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_reporting_provenance_preference.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase93-postexit-story`
  - 42 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_memory_surface.py tests\test_trade_memory_application_surface.py tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase93-postexit-memory`
  - 76 passed

### Result

- `libs/reporting/trade_report_markdown_clean.py`: 6217 lines
- `libs/reporting/trade_report_post_exit_shadow.py`: 157 lines
- Live restart: not performed.

## Phase 9.3 Slice 8 - Trade Story Evidence Helper Boundary

- Added `libs/reporting/trade_story_evidence.py`.
- Moved small evidence/provenance helpers out of `libs/reporting/trade_story_pipeline.py`:
  - substantive exit evidence detection
  - placeholder replacement
  - evidence provenance derivation
- Kept existing wrapper names in `trade_story_pipeline.py`:
  - `_has_substantive_exit_evidence`
  - `_set_or_replace_placeholder`
  - `_derive_evidence_provenance`

### Verification

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_story_pipeline.py libs\reporting\trade_story_evidence.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_reporting_provenance_preference.py -q --basetemp .pytest-work-phase93-story-evidence`
  - 39 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase93-story-evidence-ai`
  - 134 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase93-story-evidence-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_memory_surface.py tests\test_trade_memory_application_surface.py tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase93-story-evidence-memory`
  - 76 passed
- `venv\Scripts\python.exe -m pytest tests\test_intraday_trade_reports.py tests\test_symbol_trade_report.py tests\test_trade_explain_report.py -q --basetemp .pytest-work-phase93-story-evidence-render`
  - 40 passed

### Result

- `libs/reporting/trade_story_pipeline.py`: 4747 lines
- `libs/reporting/trade_story_evidence.py`: 76 lines
- Live restart: not performed.

## Phase 8.4 Slice 2 - Monitor Exit Hold Controls Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 exit/hold 제어값 해석 로직 5개를 `libs/runtime/monitor_exit/hold_controls.py`로 분리했습니다.
- 분리 대상:
  - `resolve_min_hold_sec`
  - `resolve_sell_cooldown_sec`
  - `resolve_exit_confirm_ticks`
  - `resolve_use_exit_policy`
  - `resolve_post_exit_cooldown_sec`
- 기존 테스트와 호출부 호환성을 위해 `monitor_node.py`의 private helper 이름은 import alias로 유지했습니다.

### 설계 의도

- monitor node 본문은 런타임 흐름과 의사결정 조립에 집중하게 하고, 정책/환경/상태 우선순위 해석은 `monitor_exit` 도메인 모듈로 이동했습니다.
- 장중 실제 런에 영향이 큰 exit 동작은 변경하지 않고, 기존 fallback 값과 우선순위를 보존했습니다.
- script 의존도를 늘리지 않고 runtime library 경계 안에서만 분리했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\hold_controls.py`
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase2.py -q`
  - 5 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 219 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py -q`
  - 86 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 6544 lines
- `libs/runtime/monitor_exit/hold_controls.py`: 92 lines
- 라이브 재시작 없음. 장 종료 후 리팩토링 검증만 수행했습니다.

## Phase 8.4 Slice 3 - Monitor Exit Reason Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 exit reason 분류/표시 helper를 `libs/runtime/monitor_exit/reasons.py`로 분리했습니다.
- 분리 대상:
  - `exit_reason_priority`
  - `is_emergency_exit_reason`
  - `is_hard_exit_reason`
  - `is_soft_profit_exit_reason`
  - `friendly_exit_axis`
  - `monitor_watch_axes`
- 기존 monitor node 내부 호출명은 import alias로 유지했습니다.

### 설계 의도

- exit reason의 우선순위와 hard/soft 분류는 monitor 흐름 제어보다 exit 도메인 규칙에 가깝기 때문에 별도 모듈로 고정했습니다.
- 표시용 축(`active_exit_axis`, `watch_axes`)도 exit payload와 같은 도메인에 묶어 향후 리포팅/관측 확장 시 재사용 가능하게 했습니다.
- 가격 계산, feature 조립, peak price 상태 갱신처럼 상태 변경이 얽힌 함수는 이번 조각에서 건드리지 않았습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\hold_controls.py libs\runtime\monitor_exit\reasons.py`
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase2.py -q`
  - 5 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 219 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py -q`
  - 86 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 6439 lines
- `libs/runtime/monitor_exit/reasons.py`: 118 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 4 - Monitor Exit Position Tracking Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 포지션 보유시간/peak price 추적 helper를 `libs/runtime/monitor_exit/position_tracking.py`로 분리했습니다.
- 분리 대상:
  - `position_hold_seconds`
  - `update_position_peak_price`
  - `ensure_position_peak_price_map`
- 기존 monitor node 내부 호출명은 import alias로 유지했습니다.

### 설계 의도

- 보유시간 산정과 peak price map 갱신은 exit 판단의 입력 상태를 만드는 책임이므로 monitor flow 본문에서 분리했습니다.
- 가격 선택, feature 조립, exit policy 평가가 얽힌 `preview_exit_decision` 본체는 이번 조각에서 옮기지 않았습니다.
- 상태 mutation은 기존과 동일하게 `state["persisted_state"]` 내부로 제한했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\position_tracking.py libs\runtime\monitor_exit\reasons.py libs\runtime\monitor_exit\hold_controls.py`
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase2.py -q`
  - 5 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 219 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py -q`
  - 86 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 6366 lines
- `libs/runtime/monitor_exit/position_tracking.py`: 94 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 5 - Monitor Exit Price Resolution Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 exit 가격 해석 helper를 `libs/runtime/monitor_exit/price_resolution.py`로 분리했습니다.
- 분리 대상:
  - `resolve_price`
  - `resolve_price_with_source`
  - `position_mark_price`
  - `position_mark_price_with_source`
  - `position_live_price_with_source`
- 기존 테스트 호환성을 위해 `monitor_node.py`의 private helper 이름은 import alias로 유지했습니다.

### 설계 의도

- exit 판단에 쓰는 가격 우선순위(`market.quote > position live > selected > market_snapshot > minute close`)를 monitor flow 본문에서 분리했습니다.
- 포지션 mark price fallback(`avg_price + unrealized_pnl / qty`)을 같은 모듈에 묶어 가격 출처 관리 책임을 명확히 했습니다.
- selected snapshot, feature 조립, exit policy 평가 본체는 이번 조각에서 건드리지 않았습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\price_resolution.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_price_source_resolution.py tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 220 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase2.py -q`
  - 5 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py -q`
  - 86 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 6282 lines
- `libs/runtime/monitor_exit/price_resolution.py`: 100 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 6 - Monitor Selected Snapshot Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 selected snapshot/feature 조립 helper를 `libs/runtime/monitor_exit/selected_snapshot.py`로 분리했습니다.
- 분리 대상:
  - `monitor_selected_snapshot_for_symbol`
  - `feature_alias_map`
  - `feature_context_from_state`
  - `feature_row_for_symbol`
  - `prior_bar_low_for_symbol`
- 기존 monkeypatch 테스트 호환성을 위해 `monitor_node.py`의 private helper 이름은 import alias로 유지했습니다.

### 설계 의도

- exit 판단용 selected snapshot은 가격 해석 결과, quote 보강, feature engine/ohlcv fallback을 조립하는 책임이므로 monitor flow 본문에서 분리했습니다.
- `preview_exit_decision`이 직접 다루던 입력 조립 단계를 별도 모듈로 고정해 이후 preview/evaluate 본체 이동의 전제 조건을 만들었습니다.
- 주문 lifecycle, entry evaluation, eod carry 같은 다른 monitor 책임은 건드리지 않았습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\selected_snapshot.py libs\runtime\monitor_exit\price_resolution.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_price_source_resolution.py tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 220 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase2.py -q`
  - 5 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py -q`
  - 86 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 6156 lines
- `libs/runtime/monitor_exit/selected_snapshot.py`: 140 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 7 - Monitor Runtime Clock Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 runtime clock/calendar helper를 `libs/runtime/monitor_exit/runtime_clock.py`로 분리했습니다.
- 분리 대상:
  - `monitor_runtime_dt_kst`
  - `monitor_runtime_clock_input_present`
  - `carry_calendar_context`
  - `ensure_entry_market_context_clock_fields`
- 기존 monitor node 내부 호출명은 import alias로 유지했습니다.

### 설계 의도

- EOD/overnight carry와 entry closeout guard가 공유하는 시간 해석 책임을 monitor flow 본문에서 분리했습니다.
- `minutes_to_close`의 기존 값 보존, runtime clock override, Friday weekend carry 계산 우선순위는 그대로 유지했습니다.
- EOD carry 판단 본체는 아직 옮기지 않고, 먼저 공통 시간 입력 경계만 고정했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\runtime_clock.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_price_source_resolution.py tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 220 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase2.py -q`
  - 5 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py -q`
  - 86 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 6064 lines
- `libs/runtime/monitor_exit/runtime_clock.py`: 112 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 8 - Monitor Exit Preview Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 `preview_exit_decision` 본체를 `libs/runtime/monitor_exit/preview.py`로 분리했습니다.
- `monitor_node.py`에는 기존 테스트/호출 호환용 wrapper `_preview_exit_decision_for_symbol`만 유지했습니다.
- wrapper는 기존 monkeypatch 테스트가 `monitor_node._monitor_selected_snapshot_for_symbol`을 바꾸는 구조를 보존하기 위해 selected snapshot resolver를 주입합니다.

### 설계 의도

- exit 판단 preview의 책임을 monitor flow에서 분리했습니다.
- preview 모듈은 가격 해석, selected snapshot, position tracking, exit policy map, `evaluate_exit_policy`를 조립하는 evaluator 경계입니다.
- 이번 조각으로 `select_exit_symbol`, EOD carry, 본 monitor loop가 preview 구현 세부사항을 직접 들고 있지 않게 했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\preview.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_price_source_resolution.py tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 220 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase2.py -q`
  - 5 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py -q`
  - 86 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 6003 lines
- `libs/runtime/monitor_exit/preview.py`: 97 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 9 - Monitor Exit Symbol Selection Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 exit symbol 선택 본체를 `libs/runtime/monitor_exit/selection.py`로 분리했습니다.
- `monitor_node.py`에는 기존 호출 호환용 wrapper `_select_exit_symbol`만 유지했습니다.
- wrapper는 기존 preview wrapper를 주입해 selected snapshot monkeypatch 테스트 표면을 계속 보존합니다.

### 설계 의도

- 다중 보유 상황에서 어떤 종목을 먼저 exit 평가/청산할지 고르는 책임을 monitor flow에서 분리했습니다.
- 선택 우선순위는 기존과 동일합니다:
  - exit triggered 여부
  - exit reason priority
  - pnl magnitude
  - selected symbol bonus
  - quantity
- state가 없는 구형 호출에서는 기존처럼 selected 보유 종목 또는 최대 수량 종목 fallback을 유지했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\selection.py libs\runtime\monitor_exit\preview.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_price_source_resolution.py tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 220 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase2.py -q`
  - 5 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py -q`
  - 86 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 5965 lines
- `libs/runtime/monitor_exit/selection.py`: 74 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 10 - Monitor EOD/Overnight Carry Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 EOD/overnight carry 본체를 `libs/runtime/monitor_exit/overnight_carry.py`로 분리했습니다.
- 분리 대상:
  - `persist_overnight_decision`
  - `evaluate_overnight_carry_decision`
  - `persist_eod_carry_decisions_for_open_positions`
  - `eod_carry_payload`
- `monitor_node.py`에는 기존 private helper wrapper를 유지했습니다.

### 설계 의도

- 장 마감 전 청산/오버나이트 승인 판단은 exit 도메인의 독립 정책 판단이므로 monitor flow 본문에서 분리했습니다.
- Friday weekend carry, `minutes_to_close` anomaly, non-EOD underlying exit check, persisted `overnight_decision_by_symbol` 업데이트 동작은 그대로 보존했습니다.
- 다중 보유 sweep은 기존 preview/hold wrapper를 주입받도록 하여 테스트와 운영 표면을 유지했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\overnight_carry.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py -q`
  - 107 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_price_source_resolution.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 113 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py tests\test_m21_commander_runtime_entry.py -q`
  - 91 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 5770 lines
- `libs/runtime/monitor_exit/overnight_carry.py`: 297 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 11 - Monitor Order Lifecycle Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 order lifecycle 해석 helper를 `libs/runtime/monitor_exit/order_lifecycle.py`로 분리했습니다.
- 분리 대상:
  - `derive_order_lifecycle`
  - `normalize_status`
- `monitor_node.py`의 `_derive_order_lifecycle` 이름은 import alias로 유지했습니다.

### 설계 의도

- 주문 상태 문자열, 체결 수량, 잔량을 `working`, `pending_unfilled`, `partial_fill`, `filled`, `cancelled`, `rejected`, `unknown`으로 해석하는 책임을 독립 모듈로 고정했습니다.
- pending/filled 표면과 live loop guard에 영향을 주는 로직이라 동작은 그대로 보존했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\order_lifecycle.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 219 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `libs/runtime/monitor_exit/order_lifecycle.py`: 65 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 12 - Monitor Entry Position Sizing Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 entry position sizing helper 묶음을 `libs/runtime/monitor_entry_sizing.py`로 분리했습니다.
- 분리 대상:
  - `resolve_cash`
  - `position_by_symbol`
  - `portfolio_exposure`
  - `build_sizing_risk_context`
  - `resolve_position_sizing_config`
  - `derive_position_sizing_stop_context`
- 기존 테스트가 직접 import하는 `_resolve_cash`, `_resolve_price_with_source` 표면은 alias로 유지했습니다.

### 설계 의도

- entry 후보 평가 본문에서 현금/노출/리스크 컨텍스트/구조적 손절선 산정 책임을 분리했습니다.
- sizing 정책 병합 우선순위와 구조적 stop 후보 선택 로직은 그대로 보존했습니다.
- monitor node는 entry flow 조립에 집중하고, sizing 계산은 재사용 가능한 runtime 모듈로 이동했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_entry_sizing.py libs\runtime\monitor_exit\order_lifecycle.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_cash_truth.py tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py tests\test_monitor_price_source_resolution.py -q`
  - 221 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 114 passed

### 결과

- `monitor_node.py`: 5405 lines
- `libs/runtime/monitor_entry_sizing.py`: 321 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 13 - Monitor Entry Cost Filter Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 entry cost filter 설정/평가 로직을 `libs/runtime/monitor_entry_cost_filter.py`로 분리했습니다.
- 분리 대상:
  - `resolve_entry_cost_filter_config`
  - `evaluate_entry_cost_filter`
  - cost/edge 계산 보조 함수
- 기존 테스트가 직접 import하는 `_evaluate_entry_cost_filter` 표면은 import alias로 유지했습니다.

### 설계 의도

- 진입 전 수수료/세금/왕복 비용 floor와 기대 edge 비교는 monitor entry 도메인 정책이므로 별도 모듈로 고정했습니다.
- directional edge, volatility proxy, triggered-signal proxy, quality proxy 판단은 기존과 동일하게 보존했습니다.
- monitor node 본문에서는 cost filter 결과를 받아 entry intent를 조립하는 책임만 남겼습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_entry_cost_filter.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_monitor_cash_truth.py tests\test_monitor_price_source_resolution.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 148 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py tests\test_m21_commander_runtime_entry.py -q`
  - 91 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 5019 lines
- `libs/runtime/monitor_entry_cost_filter.py`: 443 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 14 - Monitor Entry State Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 entry state/posture/transition helper를 `libs/runtime/monitor_entry_state.py`로 분리했습니다.
- 분리 대상:
  - `monitor_posture_for_cycle`
  - `load_previous_monitor_state`
  - `build_monitor_entry_state_snapshot`
  - `build_monitor_entry_transition_trace`
  - `save_current_monitor_state`
- 기존 monitor node 내부 호출명은 import alias로 유지했습니다.

### 설계 의도

- monitor loop 끝단의 posture 계산과 이전/현재 entry 상태 저장 책임을 독립 모듈로 분리했습니다.
- entry readiness 전환 추적(`became_ready_this_cycle`, reclaim/volume/breakout improvement)은 entry state 도메인으로 고정했습니다.
- monitor node 본문은 평가 결과를 조립하고 상태 저장 helper를 호출하는 형태로 줄였습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_entry_state.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_monitor_cash_truth.py tests\test_monitor_price_source_resolution.py -q`
  - 182 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py tests\test_m21_commander_runtime_entry.py -q`
  - 91 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 23 passed

### 결과

- `monitor_node.py`: 4886 lines
- `libs/runtime/monitor_entry_state.py`: 162 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 15 - Monitor Entry Controls Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 entry guard/control helper를 `libs/runtime/monitor_entry_controls.py`로 분리했습니다.
- 분리 대상:
  - `resolve_max_positions`
  - `pending_order_symbols_from_account_orders`
  - `pending_buy_symbols_from_account_orders`
  - `features_pending_order_count`
  - `resolve_block_buy_when_open_position`
  - `resolve_entry_closeout_window_guard`
- 기존 monkeypatch 테스트가 사용하는 `_resolve_entry_closeout_window_guard` 등 private helper 표면은 import alias로 유지했습니다.

### 설계 의도

- entry 후보 평가 전처리인 포지션 수 제한, 미체결 매수 차단, 보유 중 매수 차단, 장마감 근처 매수 차단 책임을 독립 모듈로 분리했습니다.
- closeout window guard는 exit policy config와 runtime clock을 사용하지만, entry gate의 입력값이므로 entry controls 모듈에 배치했습니다.
- monitor node는 entry 평가 본체에서 helper를 호출하는 구조만 유지합니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_entry_controls.py libs\runtime\monitor_entry_state.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_monitor_memory_bias.py tests\test_intraday_monitor_signals.py -q`
  - 188 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 114 passed

### 결과

- `monitor_node.py`: 4788 lines
- `libs/runtime/monitor_entry_controls.py`: 126 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 16 - Monitor Entry Policy Context Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 entry policy context helper를 `libs/runtime/monitor_entry_policy_context.py`로 분리했습니다.
- 분리 대상:
  - `resolve_monitor_memory_bias_payload`
  - `resolve_commander_entry_control_for_monitor`
  - `resolve_entry_candidate_cascade_config`
  - `build_monitor_effective_policy_trace`
  - `resolve_monitor_entry_scoring_config`
- 기존 테스트가 직접 import하는 `_resolve_monitor_entry_scoring_config` 표면은 import alias로 유지했습니다.

### 설계 의도

- commander entry control, cascade 범위, memory bias payload, effective policy trace는 entry candidate 평가 전 정책 context 조립 책임으로 묶었습니다.
- monitor node 본문은 policy context를 받아 entry 후보 평가에 넘기는 흐름만 유지합니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_entry_policy_context.py`
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase2.py tests\test_monitor_exit_guard.py tests\test_monitor_memory_bias.py -q`
  - 120 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 109 passed

### 결과

- `monitor_node.py`: 4615 lines
- `libs/runtime/monitor_entry_policy_context.py`: 191 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 17 - Monitor Strategy Hold Frame Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 strategy frame 기반 hold/exit guard helper를 `libs/runtime/monitor_strategy_frame.py`로 분리했습니다.
- 분리 대상:
  - `apply_monitor_strategy_frame`
  - `harmonize_exit_policy_with_monitor_guards`
- 기존 monitor node 내부 호출명은 import alias로 유지했습니다.

### 설계 의도

- playbook, monitor guidance, risk tone, aggressiveness, strategy horizon이 min hold/cooldown/confirm tick에 미치는 효과를 별도 모듈로 고정했습니다.
- `max_hold_sec`/`time_stop_sec`이 `min_hold_sec`보다 짧아지는 정책 충돌 보정도 같은 전략 프레임 경계에 묶었습니다.
- 큰 `apply_exit_policy_strategy_frame`은 아직 남겨두고, 먼저 hold/control 축만 분리했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_strategy_frame.py libs\runtime\monitor_entry_policy_context.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_commander_env_migration_phase2.py -q`
  - 112 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_memory_bias.py tests\test_intraday_monitor_signals.py tests\test_monitor_cash_truth.py tests\test_monitor_price_source_resolution.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 122 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 109 passed

### 결과

- `monitor_node.py`: 4485 lines
- `libs/runtime/monitor_strategy_frame.py`: 137 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 18 - Monitor Strategy Exit Policy Frame Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 전략 프레임 기반 exit policy 조정 로직을 `libs/runtime/monitor_strategy_frame.py`로 분리했습니다.
- 분리 대상:
  - `apply_exit_policy_strategy_frame`
- 기존 monitor node 호출부와 테스트 호환성을 위해 `_apply_exit_policy_strategy_frame` import alias를 유지했습니다.

### 설계 의도

- playbook, monitor guidance, risk tone, aggressiveness, strategy horizon, strategist exit policy override가 exit policy에 미치는 효과를 strategy frame 전용 런타임 모듈에 묶었습니다.
- monitor node 본문은 position/selected/state를 넘기고 결과 policy와 adjustments를 받는 흐름만 유지합니다.
- 가격 해석 의존성은 `monitor_exit.price_resolution`의 `resolve_price`, `position_mark_price`를 새 모듈에서 직접 import하도록 정리했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_strategy_frame.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_commander_env_migration_phase2.py -q`
  - 112 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_memory_bias.py tests\test_intraday_monitor_signals.py tests\test_monitor_cash_truth.py tests\test_monitor_price_source_resolution.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 122 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 109 passed

### 결과

- `monitor_node.py`: 4297 lines
- `libs/runtime/monitor_strategy_frame.py`: 514 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 19 - Monitor Minute OHLCV Runtime Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 monitor 전용 분봉 OHLCV 보강/캐시 로직을 `libs/runtime/monitor_minute_ohlcv.py`로 분리했습니다.
- 분리 대상:
  - `_ensure_monitor_minute_ohlcv_for_symbol`
  - `_resolve_monitor_skill_runner`
  - `_fresh_monitor_skill_runner`
  - `_run_monitor_minute_skill`
  - `_extract_monitor_minute_rows`
  - `_recover_monitor_minute_rows_from_history`
  - `_remember_monitor_minute_rows_in_persisted_cache`
  - `_recover_monitor_minute_rows_from_persisted_cache`
  - `_monitor_skill_output_to_record`
  - `_latest_row_ts`
  - `_minute_snapshot_age_minutes`
  - `_minute_snapshot_stale_reason`
  - `_is_trueish`
- 기존 테스트 monkeypatch 지점 유지를 위해 `monitor_node.py`에서 동일한 private 이름으로 import했습니다.

### 설계 의도

- 장중 실제 런에서 entry 평가와 매도 후 관측이 공유하는 분봉 snapshot hydration 책임을 monitor node 본문에서 분리했습니다.
- scanner seed OHLCV와 monitor 전용 minute OHLCV의 저장 경계를 별도 모듈에 고정해 이후 skill runner/캐시 정책을 독립적으로 손볼 수 있게 했습니다.
- script 의존 없이 런타임 모듈로 이동했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_minute_ohlcv.py libs\runtime\monitor_strategy_frame.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_commander_env_migration_phase2.py -q`
  - 112 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_memory_bias.py tests\test_intraday_monitor_signals.py tests\test_monitor_cash_truth.py tests\test_monitor_price_source_resolution.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 122 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 109 passed

### 결과

- `monitor_node.py`: 3641 lines
- `libs/runtime/monitor_minute_ohlcv.py`: 679 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 20 - Monitor Strategy Frame Extraction Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 전략 프레임 추출/포지션 전략 고정/정책 trace 로직을 `libs/runtime/monitor_strategy_frame.py`로 추가 분리했습니다.
- 분리 대상:
  - `extract_monitor_strategy_frame`
  - `position_strategy_frame_for_symbol`
  - `build_monitor_policy_trace`
  - `has_strategy_policy_content`
- 기존 테스트와 호출부 호환성을 위해 monitor node에서는 `_extract_monitor_strategy_frame`, `_position_strategy_frame_for_symbol`, `_build_monitor_policy_trace` alias를 유지했습니다.

### 설계 의도

- strategist output, commander horizon policy, playbook, monitor guidance, risk tone, trade aggressiveness 해석을 strategy frame 모듈에 모았습니다.
- 포지션 진입 당시 전략 context를 exit 쪽에 고정하는 책임도 같은 모듈에 배치해 exit policy 조정과 가까운 곳에서 관리하도록 했습니다.
- monitor node 본문은 strategy frame을 받아 hold/exit/trace에 전달하는 orchestration 역할만 유지합니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_strategy_frame.py libs\runtime\monitor_minute_ohlcv.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_commander_env_migration_phase2.py -q`
  - 112 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_memory_bias.py tests\test_intraday_monitor_signals.py tests\test_monitor_cash_truth.py tests\test_monitor_price_source_resolution.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 122 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 109 passed

### 결과

- `monitor_node.py`: 3307 lines
- `libs/runtime/monitor_strategy_frame.py`: 853 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 21 - Post Exit Shadow Watch Runtime Boundary

### 변경 범위

- `graphs/nodes/monitor_node.py`의 매도 후 관측 전용 shadow watchlist refresh 로직을 `libs/runtime/monitor_exit/post_exit_shadow.py`로 분리했습니다.
- 분리 대상:
  - `active_post_exit_shadow_watches`
  - `refresh_post_exit_shadow_watchlist_minute_rows`
- monitor node에는 기존 호출 호환성을 위해 `_refresh_post_exit_shadow_watchlist_minute_rows` alias를 유지했습니다.

### 설계 의도

- 실제 매매 판단과 분리된 관측-only watchlist 갱신 책임을 exit 하위 모듈에 배치했습니다.
- 분봉 snapshot 보강은 `monitor_minute_ohlcv` 모듈을 재사용하고, post-exit 관측 상태 갱신만 이 모듈이 맡도록 경계를 잡았습니다.
- monitor node는 장중 루프에서 refresh 함수를 호출하는 orchestration만 유지합니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\post_exit_shadow.py libs\runtime\monitor_minute_ohlcv.py libs\runtime\monitor_strategy_frame.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_commander_env_migration_phase2.py -q`
  - 112 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_memory_bias.py tests\test_intraday_monitor_signals.py tests\test_monitor_cash_truth.py tests\test_monitor_price_source_resolution.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 122 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 109 passed

### 결과

- `monitor_node.py`: 3215 lines
- `libs/runtime/monitor_exit/post_exit_shadow.py`: 112 lines
- 라이브 재시작 없음.

## Phase 8.4 Slice 22 - Monitor Exit Wrapper Collapse

### 변경 범위

- `graphs/nodes/monitor_node.py`에 남아 있던 단순 exit helper wrapper를 제거하고 import-time `partial` alias로 대체했습니다.
- 정리 대상:
  - `_preview_exit_decision_for_symbol`
  - `_persist_overnight_decision`
  - `_evaluate_overnight_carry_decision`
  - `_persist_eod_carry_decisions_for_open_positions`
  - `_select_exit_symbol`

### 설계 의도

- 이미 분리된 `monitor_exit.preview`, `monitor_exit.overnight_carry`, `monitor_exit.selection`의 런타임 함수를 node가 다시 감싸는 중복을 줄였습니다.
- selected snapshot resolver, hold seconds resolver, preview resolver 같은 고정 의존성만 `partial`로 묶어 기존 호출 형태를 유지했습니다.
- 다음 큰 작업인 entry candidate 평가 분리를 하기 전에 node 상단의 pass-through 코드를 정리했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\post_exit_shadow.py libs\runtime\monitor_minute_ohlcv.py libs\runtime\monitor_strategy_frame.py`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_commander_env_migration_phase2.py -q`
  - 112 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_memory_bias.py tests\test_intraday_monitor_signals.py tests\test_monitor_cash_truth.py tests\test_monitor_price_source_resolution.py tests\test_strategy_sizing_exit_upgrade.py -q`
  - 122 passed
- `venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q`
  - 109 passed

### 결과

- `monitor_node.py`: 3141 lines
- 라이브 재시작 없음.

## Phase 8.5 Slice 1 - Scanner Market Representative Guard Boundary

### 변경 범위

- Phase 8.5를 시작하고 `graphs/nodes/scanner_node.py`의 시장 대표주 guard 로직을 `libs/runtime/scanner/market_representative_guard.py`로 분리했습니다.
- 분리 대상:
  - `resolve_market_representative_guard_policy`
  - `market_representative_confirmation_sources`
  - `market_representative_top_value_dominance`
  - `apply_market_representative_guard`
  - `default_market_representative_guard_policy`
- 기존 scanner node 내부 호출 호환성을 위해 `_apply_market_representative_guard` 등 private alias를 유지했습니다.

### 설계 의도

- 삼성전자/하이닉스 같은 대표주가 단순 거래대금 우위로 rank1이 되는지 설명하는 guard 책임을 scanner 전용 런타임 모듈로 고정했습니다.
- 종목명 자체 패널티가 아니라 `top_value` dominance, score gap, confirmation sources, guard reason을 남기는 구조를 유지했습니다.
- commander를 거치지 않고 scanner를 직접 호출하는 테스트/단독 경로에서도 Kiwoom 후보 선정이면 기본 대표주 guard가 적용되도록 fallback 기본 정책을 추가했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\scanner_node.py libs\runtime\scanner\market_representative_guard.py`
- `venv\Scripts\python.exe -m pytest tests\test_scanner_bias_integration.py tests\test_scanner_fallback_policy.py tests\test_scanner_feature_hydration.py tests\test_scanner_live_symbol_filter.py tests\test_scanner_memory_bias.py tests\test_scanner_monitor_compatibility.py tests\test_scanner_policy_overlay.py tests\test_scanner_practical_selection_engine.py tests\test_scanner_quote_hydration_runtime.py tests\test_scanner_strategy_frame_integration.py tests\test_scanner_universe_candidate_metadata.py -q`
  - 64 passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`
  - 81 passed

### 결과

- `scanner_node.py`: 5147 lines
- `libs/runtime/scanner/market_representative_guard.py`: 328 lines
- 라이브 재시작 없음.

## Phase 8.5 Slice 2 - Scanner Theme Filter Boundary

### 변경 범위

- `graphs/nodes/scanner_node.py`의 테마 추출/선택/회피/필터 로직을 `libs/runtime/scanner/theme_filter.py`로 분리했습니다.
- 분리 대상:
  - `candidate_theme_match`
  - `extract_themes`
  - `extract_selected_themes`
  - `extract_avoid_themes`
  - `extract_theme_symbol_index`
  - `apply_theme_filter`
  - `apply_avoid_theme_filter`
- 기존 scanner node 내부 호출 호환성을 위해 `_extract_themes`, `_apply_theme_filter` 등 private alias를 유지했습니다.

### 설계 의도

- 후보 점수 계산 본체는 건드리지 않고, 테마가 후보 universe를 어떻게 제한하거나 회피시키는지만 별도 모듈에 고정했습니다.
- 이후 거래대금/top_value 점수와 테마 매칭 점수를 분리해서 설명할 수 있도록 theme 책임을 scanner node 본문에서 제거했습니다.
- 8.5의 핵심인 “테마와 무관한 대표주/거래대금 후보가 왜 올라왔는지”를 추적하기 위한 기반입니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\scanner_node.py libs\runtime\scanner\theme_filter.py libs\runtime\scanner\market_representative_guard.py`
- `venv\Scripts\python.exe -m pytest tests\test_scanner_bias_integration.py tests\test_scanner_fallback_policy.py tests\test_scanner_feature_hydration.py tests\test_scanner_live_symbol_filter.py tests\test_scanner_memory_bias.py tests\test_scanner_monitor_compatibility.py tests\test_scanner_policy_overlay.py tests\test_scanner_practical_selection_engine.py tests\test_scanner_quote_hydration_runtime.py tests\test_scanner_strategy_frame_integration.py tests\test_scanner_universe_candidate_metadata.py -q`
  - 64 passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`
  - 81 passed

### 결과

- `scanner_node.py`: 4895 lines
- `libs/runtime/scanner/theme_filter.py`: 236 lines
- 라이브 재시작 없음.

## Phase 8.5 Slice 3 - Scanner Candidate Pool Selection Boundary

### 변경 범위

- `graphs/nodes/scanner_node.py`의 후보 pool 구성/소스/fallback 로직을 `libs/runtime/scanner/candidate_selection.py`로 분리했습니다.
- 분리 대상:
  - `extract_strategist_candidates`
  - `resolve_candidate_source`
  - `resolve_block_static_fallback`
  - `resolve_strict_kiwoom_only`
  - `resolve_scan_aggressiveness`
  - `resolve_candidate_limit`
  - `resolve_top_candidate_pool`
  - `resolve_condition_limit`
  - `resolve_include_change_rate`
  - `resolve_enable_theme_filter`
  - `normalize_scanner_source_policy`
  - `build_kiwoom_candidates`
  - `resolve_scanner_candidates`
- `scanner_node.py`의 기존 private 호출 표면은 alias/partial로 유지하고, `extract_scanner_guidance`는 resolver로 주입했습니다.

### 설계 의도

- Kiwoom 후보 pool, condition/top value/top volume/watchlist 확장, strategist fallback, strict Kiwoom mode 판정을 scanner node 본문에서 분리했습니다.
- 테마 필터 모듈과 후보 provider를 새 candidate selection 모듈에서 조합하게 해서, 후보 pool 구성과 후단 점수 계산의 경계를 명확히 했습니다.
- 전략/commander guidance 해석은 아직 scanner node에 두고 resolver 주입으로 연결해 순환 import를 피했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\scanner_node.py libs\runtime\scanner\candidate_selection.py libs\runtime\scanner\theme_filter.py libs\runtime\scanner\market_representative_guard.py`
- `venv\Scripts\python.exe -m pytest tests\test_scanner_fallback_policy.py tests\test_scanner_live_symbol_filter.py tests\test_scanner_universe_candidate_metadata.py -q`
  - 10 passed
- `venv\Scripts\python.exe -m pytest tests\test_scanner_bias_integration.py tests\test_scanner_fallback_policy.py tests\test_scanner_feature_hydration.py tests\test_scanner_live_symbol_filter.py tests\test_scanner_memory_bias.py tests\test_scanner_monitor_compatibility.py tests\test_scanner_policy_overlay.py tests\test_scanner_practical_selection_engine.py tests\test_scanner_quote_hydration_runtime.py tests\test_scanner_strategy_frame_integration.py tests\test_scanner_universe_candidate_metadata.py -q`
  - 64 passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`
  - 81 passed

### 결과

- `scanner_node.py`: 4510 lines
- `libs/runtime/scanner/candidate_selection.py`: 454 lines

## Phase 8.5 Slice 4 - Scanner Practical Filter Boundary

### 변경 범위

- `graphs/nodes/scanner_node.py`의 실전 후보 필터링 로직을 `libs/runtime/scanner/practical_filters.py`로 분리했습니다.
- 분리 대상:
  - `candidate_quote_metrics`
  - `reduce_candidates_by_practical_filters`
  - `filter_mock_broker_restricted_candidates`
  - `resolve_min_trading_value`
  - `resolve_min_volume`
  - `resolve_exclude_halted`
- 기존 테스트와 내부 호출 호환성을 위해 `scanner_node.py`에는 `_candidate_quote_metrics`, `_reduce_candidates_by_practical_filters`, `_filter_mock_broker_restricted_candidates` alias를 유지했습니다.

### 설계 의도

- 후보 pool 구성과 후보 실전 필터링을 분리했습니다.
- 거래대금/거래량/거래정지/이상종목/모의 broker 제한 같은 실행 직전 후보 품질 경계를 scanner 본문 밖으로 옮겨, 이후 정책 강화나 broker별 제한 추가가 scanner 대형 파일을 다시 키우지 않도록 했습니다.
- mock 후보 metric fallback, raw quote 보정, ETF 괴리 신호 포함 방식은 기존 동작을 유지했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\scanner_node.py libs\runtime\scanner\practical_filters.py libs\runtime\scanner\candidate_selection.py libs\runtime\scanner\theme_filter.py libs\runtime\scanner\market_representative_guard.py`
- `venv\Scripts\python.exe -m pytest tests\test_scanner_strategy_frame_integration.py tests\test_scanner_practical_selection_engine.py tests\test_scanner_quote_hydration_runtime.py -q`
  - 19 passed
- `venv\Scripts\python.exe -m pytest tests\test_scanner_fallback_policy.py tests\test_scanner_live_symbol_filter.py tests\test_scanner_universe_candidate_metadata.py -q`
  - 10 passed
- `venv\Scripts\python.exe -m pytest tests\test_scanner_bias_integration.py tests\test_scanner_fallback_policy.py tests\test_scanner_feature_hydration.py tests\test_scanner_live_symbol_filter.py tests\test_scanner_memory_bias.py tests\test_scanner_monitor_compatibility.py tests\test_scanner_policy_overlay.py tests\test_scanner_practical_selection_engine.py tests\test_scanner_quote_hydration_runtime.py tests\test_scanner_strategy_frame_integration.py tests\test_scanner_universe_candidate_metadata.py -q`
  - 64 passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`
  - 81 passed

### 결과

- `scanner_node.py`: 4288 lines
- `libs/runtime/scanner/practical_filters.py`: 245 lines

## Phase 8.5 Slice 5 - Scanner Output Snapshot Boundary

### 변경 범위

- `graphs/nodes/scanner_node.py`의 후보 관측/출력 snapshot 생성 로직을 `libs/runtime/scanner/output_snapshots.py`로 분리했습니다.
- 분리 대상:
  - `compact_selected_snapshot`
  - `feature_coverage_summary`
  - `compact_feature_snapshot`
  - `ranking_table_rows`
- scanner node에는 기존 private 호출면을 유지하기 위해 `_compact_selected_snapshot`, `_feature_coverage_summary`, `_compact_feature_snapshot`, `_ranking_table_rows` alias를 남겼습니다.

### 설계 의도

- 후보 선정 핵심 점수 계산과 관측용 payload 조립을 분리했습니다.
- 리포트/아티팩트에 보여줄 ranking table, selected snapshot, feature coverage를 독립 모듈로 빼서 추후 보고서 필드 추가가 scanner 본문을 다시 키우지 않도록 했습니다.
- theme match 판정은 기존 theme filter 모듈을 재사용하게 했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\scanner_node.py libs\runtime\scanner\output_snapshots.py libs\runtime\scanner\practical_filters.py`
- `venv\Scripts\python.exe -m pytest tests\test_scanner_strategy_frame_integration.py tests\test_scanner_practical_selection_engine.py tests\test_scanner_quote_hydration_runtime.py -q`
  - 19 passed
- `venv\Scripts\python.exe -m pytest tests\test_scanner_fallback_policy.py tests\test_scanner_live_symbol_filter.py tests\test_scanner_universe_candidate_metadata.py -q`
  - 10 passed
- `venv\Scripts\python.exe -m pytest tests\test_scanner_bias_integration.py tests\test_scanner_fallback_policy.py tests\test_scanner_feature_hydration.py tests\test_scanner_live_symbol_filter.py tests\test_scanner_memory_bias.py tests\test_scanner_monitor_compatibility.py tests\test_scanner_policy_overlay.py tests\test_scanner_practical_selection_engine.py tests\test_scanner_quote_hydration_runtime.py tests\test_scanner_strategy_frame_integration.py tests\test_scanner_universe_candidate_metadata.py -q`
  - 64 passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`
  - 81 passed

### 결과

- `scanner_node.py`: 4097 lines
- `libs/runtime/scanner/output_snapshots.py`: 209 lines

## Phase 9.1 Slice 1 - Daily Report Freshness and Symbol Refresh Boundary

### 변경 범위

- `libs/reporting/daily_report_generator.py`에서 freshness 계산과 symbol report refresh 로직을 분리했습니다.
- 신규 모듈:
  - `libs/reporting/daily_report_runtime/freshness.py`
  - `libs/reporting/daily_report_runtime/symbol_refresh.py`
- 원 계획의 `libs/reporting/daily_report/...` 경로는 기존 `libs/reporting/daily_report.py` 파일과 충돌하므로 `daily_report_runtime` 패키지로 우회했습니다.
- generator 쪽 private helper 이름은 import alias로 유지했습니다.

### 설계 의도

- daily report 본문 생성에서 데이터 freshness 판정과 symbol report refresh 정책을 분리했습니다.
- symbol report mode, stale 판정, expected trade id coverage 계산을 별도 모듈로 옮겨 이후 symbol별 refresh 정책을 확장하기 쉽게 했습니다.
- operator summary snapshot 생성 함수는 테스트 monkeypatch 지점을 유지하기 위해 generator에 남겼습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile libs\reporting\daily_report_generator.py libs\reporting\daily_report_runtime\freshness.py libs\reporting\daily_report_runtime\symbol_refresh.py`
- `venv\Scripts\python.exe -m pytest tests\test_daily_report.py -q --basetemp .pytest-work-daily-phase9`
  - 9 passed
- `venv\Scripts\python.exe -m pytest tests\test_operator_summary_reports.py -q --basetemp .pytest-work-ops-phase9`
  - 16 passed

### 결과

- `libs/reporting/daily_report_generator.py`: 568 lines
- `libs/reporting/daily_report_runtime/freshness.py`: 115 lines
- `libs/reporting/daily_report_runtime/symbol_refresh.py`: 105 lines
- 라이브 재시작 없음.

## Phase 9.1 Slice 2 - Daily Report Event Build Model Boundary

### 변경 범위

- daily report 이벤트 rows/day bucketing과 기본 일간 event summary 생성을 `libs/reporting/daily_report_runtime/build_model.py`로 분리했습니다.
- 분리 대상:
  - `day_key`
  - `build_event_rows`
  - `build_basic_daily_event_summary`

### 설계 의도

- report model 구성과 markdown rendering을 분리하기 위한 첫 단계입니다.
- stage/event/action/approval/block 카운터 계산을 generator 본문 밖으로 옮겨 이후 build_model 확장을 독립적으로 진행할 수 있게 했습니다.
- mojibake가 포함된 markdown 문자열 함수는 이번 슬라이스에서 건드리지 않았습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile libs\reporting\daily_report_generator.py libs\reporting\daily_report_runtime\build_model.py libs\reporting\daily_report_runtime\freshness.py libs\reporting\daily_report_runtime\symbol_refresh.py`
- `venv\Scripts\python.exe -m pytest tests\test_daily_report.py -q --basetemp .pytest-work-daily-phase9b`
  - 9 passed
- `venv\Scripts\python.exe -m pytest tests\test_operator_summary_reports.py -q --basetemp .pytest-work-ops-phase9b`
  - 16 passed

### 결과

- `libs/reporting/daily_report_generator.py`: 517 lines
- `libs/reporting/daily_report_runtime/build_model.py`: 80 lines
- 라이브 재시작 없음.

## Phase 9.1 Slice 3 - Daily Report Markdown Boundary

### 변경 범위

- daily report markdown 조립 로직을 `libs/reporting/daily_report_runtime/markdown.py`로 분리했습니다.
- 분리 대상:
  - operator summary snapshot section
  - route provenance section
  - narrative axis policy section
  - policy surface quality section
  - chart structure decision hint section
  - top issues section
  - recommended operator actions section
  - no-event daily markdown renderer
  - normal daily markdown renderer

### 설계 의도

- daily report generator가 markdown 문자열 조립을 직접 담당하지 않도록 했습니다.
- 기존 잔여 보유 종목 markdown 함수는 mojibake 문자열이 포함되어 있어 이번 슬라이스에서는 이동하지 않고 renderer callback으로 연결했습니다.
- report 출력 필드와 문장 내용은 유지했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile libs\reporting\daily_report_generator.py libs\reporting\daily_report_runtime\markdown.py libs\reporting\daily_report_runtime\build_model.py libs\reporting\daily_report_runtime\freshness.py libs\reporting\daily_report_runtime\symbol_refresh.py`
- `venv\Scripts\python.exe -m pytest tests\test_daily_report.py -q --basetemp .pytest-work-daily-phase9c`
  - 9 passed
- `venv\Scripts\python.exe -m pytest tests\test_operator_summary_reports.py -q --basetemp .pytest-work-ops-phase9c`
  - 16 passed

### 결과

- `libs/reporting/daily_report_generator.py`: 334 lines
- `libs/reporting/daily_report_runtime/markdown.py`: 244 lines
- 라이브 재시작 없음.

## Phase 9.1 Slice 4 - Daily Report Payload Build Model Boundary

### 변경 범위

- daily report payload 구성 로직을 `libs/reporting/daily_report_runtime/build_model.py`로 추가 분리했습니다.
- 분리 대상:
  - `build_no_event_daily_payload`
  - `enrich_daily_summary_payload`

### 설계 의도

- generator 본문에서 dict 필드 조립을 제거하고, report model 구성 책임을 build_model 모듈로 이동했습니다.
- generator는 이벤트 로딩, 보조 snapshot 로딩, 파일 쓰기, operator summary artifact 생성 orchestration 중심으로 축소했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile libs\reporting\daily_report_generator.py libs\reporting\daily_report_runtime\markdown.py libs\reporting\daily_report_runtime\build_model.py libs\reporting\daily_report_runtime\freshness.py libs\reporting\daily_report_runtime\symbol_refresh.py`
- `venv\Scripts\python.exe -m pytest tests\test_daily_report.py -q --basetemp .pytest-work-daily-phase9d`
  - 9 passed
- `venv\Scripts\python.exe -m pytest tests\test_operator_summary_reports.py -q --basetemp .pytest-work-ops-phase9d`
  - 16 passed

### 결과

- `libs/reporting/daily_report_generator.py`: 317 lines
- `libs/reporting/daily_report_runtime/build_model.py`: 169 lines
- 라이브 재시작 없음.

## Phase 9.2 Slice 1 - Metrics Report Event Extractor Boundary

### 변경 범위

- `libs/reporting/metrics_report_generator.py`의 이벤트 추출/정규화 helper를 `libs/reporting/metrics_report/event_extractors.py`로 분리했습니다.
- 신규 패키지:
  - `libs/reporting/metrics_report/__init__.py`
  - `libs/reporting/metrics_report/event_extractors.py`
- 분리 대상:
  - timestamp epoch/day 변환
  - decision intent action 추출
  - guard reason 추출
  - API id 추출
  - 429 error 판정
  - skill error tag 정규화

### 검증

- `venv\Scripts\python.exe -m py_compile libs\reporting\metrics_report_generator.py libs\reporting\metrics_report\event_extractors.py`
- `venv\Scripts\python.exe -m pytest tests\test_generate_metrics_report.py tests\test_m23_9_commander_resilience_metrics_report.py tests\test_m29_5_monitor_metrics_report.py -q --basetemp .pytest-work-metrics-phase92a`
  - 13 passed
- `venv\Scripts\python.exe -m pytest tests\test_report_metadata_alignment.py tests\test_reporter_service.py -q --basetemp .pytest-work-metrics-phase92b`
  - 5 passed

### 결과

- `libs/reporting/metrics_report_generator.py`: 1017 lines
- `libs/reporting/metrics_report/event_extractors.py`: 162 lines

## Phase 9.2 Slice 2 - Metrics Report Aggregator Helper Boundary

### 변경 범위

- 숫자 summary, latency summary, generated timestamp, epoch iso 변환 helper를 `libs/reporting/metrics_report/aggregators.py`로 분리했습니다.
- 이후 같은 모듈에 event row build와 empty metrics summary 생성도 추가했습니다.

### 설계 의도

- metrics aggregation에 필요한 공통 계산을 generator 본문에서 분리했습니다.
- no-event schema payload를 별도 함수로 고정해 빈 리포트 schema 유지 부담을 낮췄습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile libs\reporting\metrics_report_generator.py libs\reporting\metrics_report\event_extractors.py libs\reporting\metrics_report\aggregators.py`
- `venv\Scripts\python.exe -m pytest tests\test_generate_metrics_report.py tests\test_m23_9_commander_resilience_metrics_report.py tests\test_m29_5_monitor_metrics_report.py -q --basetemp .pytest-work-metrics-phase92e`
  - 13 passed
- `venv\Scripts\python.exe -m pytest tests\test_report_metadata_alignment.py tests\test_reporter_service.py -q --basetemp .pytest-work-metrics-phase92f`
  - 5 passed

### 결과

- `libs/reporting/metrics_report_generator.py`: 543 lines
- `libs/reporting/metrics_report/aggregators.py`: 188 lines

## Phase 9.2 Slice 3 - Metrics Report Markdown Boundary

### 변경 범위

- metrics markdown 렌더링을 `libs/reporting/metrics_report/markdown.py`로 분리했습니다.
- 분리 대상:
  - empty metrics markdown
  - normal metrics markdown
  - execution, strategist LLM, skill hydration, commander resilience, portfolio guard, monitor, no-trade, route provenance, latency, broker API sections

### 설계 의도

- JSON summary 구성과 markdown rendering을 분리했습니다.
- generator는 이벤트 집계와 파일 쓰기 orchestration 중심으로 축소했습니다.

### 검증

- `venv\Scripts\python.exe -m py_compile libs\reporting\metrics_report_generator.py libs\reporting\metrics_report\markdown.py libs\reporting\metrics_report\event_extractors.py libs\reporting\metrics_report\aggregators.py`
- `venv\Scripts\python.exe -m pytest tests\test_generate_metrics_report.py tests\test_m23_9_commander_resilience_metrics_report.py tests\test_m29_5_monitor_metrics_report.py -q --basetemp .pytest-work-metrics-phase92c`
  - 13 passed
- `venv\Scripts\python.exe -m pytest tests\test_report_metadata_alignment.py tests\test_reporter_service.py -q --basetemp .pytest-work-metrics-phase92d`
  - 5 passed
- `venv\Scripts\python.exe -m pytest tests\test_reporter_script_wrappers.py tests\test_m25_1_metrics_schema_freeze_v1.py -q --basetemp .pytest-work-metrics-phase92g`
  - 8 passed

### 결과

- `libs/reporting/metrics_report_generator.py`: 543 lines
- `libs/reporting/metrics_report/markdown.py`: 234 lines
- 라이브 재시작 없음.
- 라이브 재시작 없음.
- 라이브 재시작 없음.
- 라이브 재시작 없음.
