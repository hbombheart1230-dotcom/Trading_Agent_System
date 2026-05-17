# 2026-05-15 Incremental Refactor Plan Start

## Summary

Created the detailed incremental refactor plan for reducing hot-path risk without a large rewrite.

Main plan:

- `docs/dev/incremental_refactor_plan_2026-05-15.md`

## Scope

No runtime behavior was changed by this planning step.

The plan covers:

- Monitor exit boundary
- Monitor entry boundary
- Executor order lifecycle
- Reporter truth boundary
- Strategist/scanner policy surface
- Script/runtime boundary cleanup
- Documentation and repository hygiene
- Regression and live restart policy

## First Recommended Slice

Phase 1.1:

- Extract VWAP breakdown confirmation from `graphs/nodes/monitor_node.py`
- Target module: `libs/runtime/monitor_exit_confirmation.py`
- Preserve current behavior and field names
- Validate with focused Monitor/Exit tests

## Baseline Notes

- Test collection baseline observed: `1979 tests collected`
- Existing runtime boundary/doc smoke observed: `3 passed`

## Remaining Work

- Continue Phase 1.3 only after live behavior is stable.
- Keep each extraction behavior-preserving unless explicitly marked as a behavior patch.

## Phase 1.1 Started

Extracted VWAP breakdown confirmation helper into:

- `libs/runtime/monitor_exit_confirmation.py`

Monitor now imports and calls the helper instead of owning that calculation inline.

Behavior target:

- no change to trading behavior
- no change to output field names
- no change to VWAP confirmation semantics

## Validation

Focused VWAP/exit tests:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py::test_monitor_vwap_breakdown_exit_after_two_minute_confirmations tests\test_monitor_exit_guard.py::test_monitor_vwap_breakdown_exit_uses_feature_signal tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
41 passed
```

Monitor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
219 passed
```

## Phase 6.1 Runtime Health Script Boundary Split

Extracted reusable Phase 5 runtime health aggregation/rendering logic into:

- `libs/reporting/phase_runtime_health.py`

Kept the CLI entrypoint as a thin wrapper:

- `scripts/check_phase_5_2_5_3_runtime_health.py`

Updated runtime/reporting library code:

- `libs/reporting/report_source_helpers.py` now imports the health builder from `libs.reporting.phase_runtime_health`
- `tests/test_runtime_entrypoint_import_boundaries.py` now guards `report_source_helpers.py` against reintroducing direct `scripts.*` imports

Design intent:

- preserve existing CLI behavior and test-facing function names
- stop library/report source assembly code from depending on a script file
- make the runtime health builder reusable as a stable reporting module
- keep remaining script boundary cleanup incremental instead of moving all script wrappers at once

Behavior target:

- no change to health payload schema
- no change to CLI arguments or text rendering
- no change to report source fallback behavior

## Phase 6.1 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile libs\reporting\phase_runtime_health.py scripts\check_phase_5_2_5_3_runtime_health.py libs\reporting\report_source_helpers.py
```

Result:

```text
passed
```

Focused boundary/report tests:

```text
venv\Scripts\python.exe -m pytest tests\test_check_phase_5_2_5_3_runtime_health.py tests\test_reporter_script_wrappers.py tests\test_runtime_entrypoint_import_boundaries.py tests\test_trade_summary_symbol_metadata.py tests\test_generate_metrics_report.py -q
```

Result:

```text
22 passed
```

## Phase 6.3 Metrics Report Script Boundary Split

Extracted canonical metrics report generation into:

- `libs/reporting/metrics_report_generator.py`

Kept the script as a thin CLI/public compatibility wrapper:

- `scripts/generate_metrics_report.py`

Updated library call sites:

- `libs/agent/reporter.py` now calls metrics generation from `libs`
- `libs/reporting/operator_visibility.py` now generates missing metrics through `libs.reporting.metrics_report_generator`
- `libs/reporting/reporter_feedback.py` now generates missing metrics through `libs.reporting.metrics_report_generator`

Updated tests:

- runtime boundary test now guards `libs/reporting/metrics_report_generator.py`, `operator_visibility.py`, and `reporter_feedback.py`

Design intent:

- preserve existing script API and CLI behavior
- keep report generation reusable from the reporting layer
- remove the main remaining reporting-layer dependency on `scripts.generate_metrics_report`

Behavior target:

- no change to metrics report artifact names
- no change to metrics JSON/Markdown schema
- no change to `Reporter.generate_metrics_report` output contract

## Phase 6.3 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile libs\reporting\metrics_report_generator.py libs\agent\reporter.py libs\reporting\operator_visibility.py libs\reporting\reporter_feedback.py scripts\generate_metrics_report.py
```

Result:

```text
passed
```

Focused metrics/report tests:

```text
venv\Scripts\python.exe -m pytest tests\test_generate_metrics_report.py tests\test_m23_9_commander_resilience_metrics_report.py tests\test_m29_5_monitor_metrics_report.py tests\test_report_metadata_alignment.py tests\test_reporter_script_wrappers.py tests\test_reporter_service.py tests\test_operator_visibility_reports.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
37 passed
```

## Phase 6.4 API Catalog Builder Boundary Split

Extracted API catalog build logic into:

- `libs/catalog/api_catalog_builder.py`

Kept the script as a thin compatibility wrapper:

- `scripts/build_api_catalog.py`

Updated library call sites:

- `libs/read/kiwoom_broker_truth_common.py` now calls `libs.catalog.api_catalog_builder.build_api_catalog`

Updated tests:

- runtime boundary test now guards `libs/read/kiwoom_broker_truth_common.py`

Design intent:

- keep catalog construction with catalog-layer code
- stop broker truth readers from importing a script module
- preserve the existing script command for manual/demo use

Behavior target:

- no change to default input files
- no change to default output path
- no change to merged API catalog schema

## Phase 6.4 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile libs\catalog\api_catalog_builder.py scripts\build_api_catalog.py libs\read\kiwoom_broker_truth_common.py
```

Result:

```text
passed
```

Focused catalog/broker truth tests:

```text
venv\Scripts\python.exe -m pytest tests\test_build_api_catalog.py tests\test_kiwoom_day_pnl_reader.py tests\test_kiwoom_order_fill_reader.py tests\test_kiwoom_orderable_cash_reader.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
11 passed
```

Remaining `libs` search:

```text
rg -n "from scripts|import scripts|scripts\." libs
```

Result:

```text
Only runtime command/path strings remain in live loop process matching and session entry dispatch.
No remaining direct libs -> scripts import was found.
```

## Phase 7.1 Session Entrypoint Library Split

Moved runtime session entry implementations out of `scripts` into:

- `libs/runtime/entrypoints/live_session_summary.py`
- `libs/runtime/entrypoints/live_session_watch.py`
- `libs/runtime/entrypoints/commander_runtime_once.py`
- `libs/runtime/entrypoints/m31_agent_chain_probe.py`
- `libs/runtime/entrypoints/offhours_validation_loop.py`
- `libs/runtime/entrypoints/m13_live_loop.py`
- `libs/runtime/entrypoints/mock_exam_day.py`

Kept the corresponding `scripts/run_*.py` files as thin CLI compatibility wrappers only.

Updated dispatch:

- `libs/runtime/session_entry_dispatch.py` now resolves all session implementation ids to `libs.runtime.entrypoints.*`
- `scripts/run_session.py` reports library implementation paths in its execution plan
- `live_session_watch` now runs summary via `python -m libs.runtime.entrypoints.live_session_summary`, not a script file path
- `live_loop_process_query.py` now detects direct backend processes by `-m libs.runtime.entrypoints.m13_live_loop`

Design intent:

- treat `scripts` as compatibility launchers, not implementation owners
- keep runtime implementations importable/testable from `libs`
- reduce string-level `scripts.*` coupling in the session dispatcher

Behavior target:

- no change to CLI arguments
- no change to session plans except implementation path strings
- no change to mock exam orchestration schema
- no change to live loop locking behavior

## Phase 7.1 Validation

Syntax checks:

```text
venv\Scripts\python.exe -m py_compile libs\runtime\entrypoints\live_session_summary.py libs\runtime\entrypoints\live_session_watch.py scripts\run_live_session_summary.py scripts\run_live_session_watch.py libs\runtime\session_entry_dispatch.py scripts\run_session.py
venv\Scripts\python.exe -m py_compile libs\runtime\entrypoints\commander_runtime_once.py libs\runtime\entrypoints\m31_agent_chain_probe.py libs\runtime\entrypoints\offhours_validation_loop.py scripts\run_commander_runtime_once.py scripts\run_m31_agent_chain_probe.py scripts\run_offhours_validation_loop.py libs\runtime\session_entry_dispatch.py scripts\run_session.py
venv\Scripts\python.exe -m py_compile libs\runtime\entrypoints\m13_live_loop.py scripts\run_m13_live_loop.py libs\runtime\session_entry_dispatch.py scripts\run_session.py
venv\Scripts\python.exe -m py_compile libs\runtime\entrypoints\mock_exam_day.py scripts\run_mock_exam_day.py libs\runtime\session_entry_dispatch.py scripts\run_session.py
```

Result:

```text
passed
```

Focused session entrypoint tests:

```text
venv\Scripts\python.exe -m pytest tests\test_run_live_session_watch.py tests\test_run_live_session_summary.py tests\test_m21_runtime_once_script.py tests\test_m23_6_operator_intervention_resume.py tests\test_m31_agent_chain_probe.py tests\test_offhours_validation_loop.py tests\test_run_m13_live_loop_lock.py tests\test_run_mock_exam_day.py tests\test_session_entry_dispatch.py tests\test_run_session.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
56 passed
```

Additional checks:

```text
venv\Scripts\python.exe -m pytest tests\test_live_loop_process_query.py tests\test_run_mock_exam_day.py tests\test_session_entry_dispatch.py tests\test_run_session.py -q
venv\Scripts\python.exe -m pytest tests\test_m28_4_startup_preflight_check.py -q
```

Result:

```text
23 passed
3 passed
```

Remaining `libs` search:

```text
rg -n "from scripts|import scripts|scripts\." libs
```

Result:

```text
Only the official run_session process-detection string remains:
libs/runtime/live_loop_process_query.py checks scripts/run_session.py or -m scripts.run_session.
```

## Phase 7.2 M28 Preflight And Launch Entrypoint Split

Moved M28 preflight/launch implementation code into:

- `libs/runtime/entrypoints/check_runtime_profile.py`
- `libs/runtime/entrypoints/m28_startup_preflight_check.py`
- `libs/runtime/entrypoints/launch_with_preflight.py`
- `libs/runtime/entrypoints/m28_runtime_profile_scaffold_check.py`
- `libs/runtime/entrypoints/m28_runtime_lifecycle_hooks_check.py`
- `libs/runtime/entrypoints/m28_rollout_rollback_check.py`
- `libs/runtime/entrypoints/m28_scheduler_worker_launch_wrapper_check.py`
- `libs/runtime/entrypoints/m28_launch_hook_integration_check.py`
- `libs/runtime/entrypoints/m28_deploy_launch_template_check.py`
- `libs/runtime/entrypoints/m28_registration_helper_check.py`
- `libs/runtime/entrypoints/m28_closeout_check.py`
- `libs/runtime/entrypoints/m28_launch_templates.py`
- `libs/runtime/entrypoints/m28_registration_helpers.py`

Kept the matching `scripts/*` files as compatibility wrappers.

Updated internal imports:

- M28 closeout now imports M28 checks from `libs.runtime.entrypoints`
- rollout/rollback now imports lifecycle/profile checks from `libs.runtime.entrypoints`
- launch hook now imports `launch_with_preflight` from `libs.runtime.entrypoints`
- deploy template and registration helper checks now import their generators from `libs.runtime.entrypoints`
- generated launch templates now point at `python -m libs.runtime.entrypoints.*` commands instead of script file paths

Design intent:

- keep M28 implementation code in a stable runtime package
- reduce script-to-script dependency chains
- preserve script compatibility for existing operators and tests that execute script files directly

Behavior target:

- no change to M28 report schemas
- no change to CLI arguments
- no change to wrapper check pass/fail semantics

## Phase 7.2 Validation

Syntax check:

```text
$files = @(rg --files libs\runtime\entrypoints scripts | Where-Object { $_ -match '(m28_|launch_with_preflight|check_runtime_profile)' -and $_ -match '\.py$' }); venv\Scripts\python.exe -m py_compile @files
```

Result:

```text
passed
```

Focused M28 tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m28_1_runtime_profile_scaffold.py tests\test_m28_2_runtime_lifecycle_hooks.py tests\test_m28_3_rollout_rollback_check.py tests\test_m28_4_startup_preflight_check.py tests\test_m28_5_scheduler_worker_launch_wrapper_check.py tests\test_m28_6_launch_hook_integration_check.py tests\test_m28_7_deploy_launch_templates.py tests\test_m28_8_registration_helpers.py tests\test_m28_9_closeout_check.py -q
```

Result:

```text
33 passed
```

Dependency check:

```text
rg -n "from scripts\.(run_m28|generate_m28|check_runtime_profile|launch_with_preflight)" scripts libs tests
```

Result:

```text
No matches.
```

## Course Correction - Large File Modularization Back On Track

After Phase 7.1/7.2, implementation ownership moved from `scripts` to `libs`, but some large files were still large files under a better package path. That helped dependency direction but did not fully satisfy the original modularity goal.

Corrected priority from here:

- primary: reduce large files by responsibility
- primary: isolate stable helper/policy/process/rendering code into modules that rarely need edits
- secondary: keep script wrappers thin

Current high-priority large files:

- `libs/runtime/entrypoints/mock_exam_day.py`
- `libs/reporting/daily_report_generator.py`
- `libs/reporting/metrics_report_generator.py`
- `libs/reporting/trade_report_markdown_clean.py`
- `libs/reporting/trade_report_ai.py`

## Phase 7.3 Mock Exam Day Process Boundary Split

Extracted stable mock-exam-day helpers into:

- `libs/runtime/mock_exam_day/common.py`
- `libs/runtime/mock_exam_day/processes.py`

Moved out of `libs/runtime/entrypoints/mock_exam_day.py`:

- UTC/time/path/env JSONL helpers
- subprocess execution wrapper
- background process startup wrapper
- live loop process owner/chain selection
- existing live loop detection
- closeout live loop stop helper

Kept compatibility names in the entrypoint so existing tests and emergency monkeypatch points still work:

- `_run_subprocess`
- `_start_live_loop_background`
- `_start_background_command`
- `_existing_live_loop_step`
- `_stop_live_loop_processes`
- `_background_creationflags`

Design intent:

- leave `mock_exam_day.py` focused on phase orchestration
- put OS/process interaction into a dedicated module
- preserve current behavior and patch points

Size impact:

```text
libs/runtime/entrypoints/mock_exam_day.py: 1325 -> 1020 lines
libs/runtime/mock_exam_day/common.py: 85 lines
libs/runtime/mock_exam_day/processes.py: 265 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile libs\runtime\entrypoints\mock_exam_day.py libs\runtime\mock_exam_day\common.py libs\runtime\mock_exam_day\processes.py
venv\Scripts\python.exe -m pytest tests\test_run_mock_exam_day.py tests\test_session_entry_dispatch.py tests\test_run_session.py -q
```

Result:

```text
22 passed
```

## Phase 7.4 Mock Exam Day Closeout Liquidation Split

Extracted closeout backup-liquidation policy into:

- `libs/runtime/mock_exam_day/closeout_liquidation.py`

Moved out of `libs/runtime/entrypoints/mock_exam_day.py`:

- state-store path resolution for closeout
- execution-mode normalization for closeout broker truth handling
- mock/broker portfolio row normalization
- broker portfolio truth read helper
- position metadata merge/filter helpers
- closeout backup liquidation state mutation policy

Kept compatibility wrappers in the entrypoint for existing tests and emergency patch points:

- `_resolve_state_store_path`
- `_to_float`
- `_resolve_execution_mode_from_env`
- `_normalize_position_row`
- `_read_authoritative_portfolio_rows`
- `_merge_position_metadata`
- `_filter_state_position_metadata`
- `_closeout_backup_liquidation`

Design intent:

- keep closeout liquidation policy in a stable module that rarely needs edits
- leave `mock_exam_day.py` closer to phase orchestration only
- preserve existing monkeypatch behavior for broker-truth tests
- make future closeout rules local to `runtime/mock_exam_day/closeout_liquidation.py`

Size impact:

```text
libs/runtime/entrypoints/mock_exam_day.py: 1020 -> 718 lines
libs/runtime/mock_exam_day/closeout_liquidation.py: 334 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile libs\runtime\entrypoints\mock_exam_day.py libs\runtime\mock_exam_day\closeout_liquidation.py
venv\Scripts\python.exe -m pytest tests\test_run_mock_exam_day.py tests\test_session_entry_dispatch.py tests\test_run_session.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
24 passed
```

## Phase 7.5 Mock Exam Day Closeout Phase Split

Extracted closeout phase step orchestration into:

- `libs/runtime/mock_exam_day/closeout_phase.py`

Moved out of `libs/runtime/entrypoints/mock_exam_day.py`:

- closeout stop-loop step ordering
- closeout backup-liquidation step attachment
- SLO incident report command construction
- metrics report environment setup
- operator summary command construction
- optional decision-story/run-card report gating
- daily report command construction
- reporter-analysis/live-execution-bundle command construction
- report inventory maintenance command construction
- closeout phase failure aggregation

The entrypoint now delegates closeout orchestration through injected callbacks:

- `_run_subprocess`
- `_stop_live_loop_processes`
- `_closeout_backup_liquidation`

Design intent:

- keep mutable closeout report sequencing in one module
- keep `mock_exam_day.py` focused on CLI parsing, common context, and phase dispatch
- preserve existing monkeypatch points used by tests and emergency runtime checks

Size impact:

```text
libs/runtime/entrypoints/mock_exam_day.py: 718 -> 496 lines
libs/runtime/mock_exam_day/closeout_phase.py: 253 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile libs\runtime\entrypoints\mock_exam_day.py libs\runtime\mock_exam_day\closeout_phase.py
venv\Scripts\python.exe -m pytest tests\test_run_mock_exam_day.py tests\test_session_entry_dispatch.py tests\test_run_session.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
24 passed
```

## Phase 7.6 Mock Exam Day Preopen/Session Phase Split

Extracted remaining preopen/session phase orchestration into:

- `libs/runtime/mock_exam_day/preopen_phase.py`
- `libs/runtime/mock_exam_day/session_phase.py`

Moved out of `libs/runtime/entrypoints/mock_exam_day.py`:

- M30 final signoff command construction
- M30 post-golive policy command construction
- M31 mock exam readiness command and fallback-day handling
- preopen runtime-mode gate attachment
- session runtime-mode gate
- market-hours/offhours session branching
- offhours one-shot probe command construction
- offhours simulated session background loop command construction
- live loop reuse/launch step attachment

The entrypoint now delegates phase execution through injected callbacks:

- `_run_subprocess`
- `_start_live_loop_background`
- `_start_background_command`
- `_existing_live_loop_step`
- `_runtime_mode_checks`

Design intent:

- make `mock_exam_day.py` primarily CLI parsing, common context construction, phase dispatch, and report writeout
- keep preopen/session behavior in focused modules with stable responsibilities
- preserve existing monkeypatch points for tests and emergency runtime checks

Size impact:

```text
libs/runtime/entrypoints/mock_exam_day.py: 496 -> 258 lines
libs/runtime/mock_exam_day/preopen_phase.py: 172 lines
libs/runtime/mock_exam_day/session_phase.py: 168 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile libs\runtime\entrypoints\mock_exam_day.py libs\runtime\mock_exam_day\preopen_phase.py libs\runtime\mock_exam_day\session_phase.py libs\runtime\mock_exam_day\closeout_phase.py
venv\Scripts\python.exe -m pytest tests\test_run_mock_exam_day.py tests\test_session_entry_dispatch.py tests\test_run_session.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
24 passed
```

## Revised Runtime-First Plan

After checking the active live session process, the current intraday route is:

```text
scripts/run_session.py
-> libs/runtime/entrypoints/m13_live_loop.py
-> graphs/pipelines/m13_live_loop.py
-> graphs/pipelines/m13_tick.py
-> graphs/commander_runtime.py
-> integrated_chain
```

The remaining reporting modularization plan is still valid, but it moves behind actual intraday runtime cleanup.

New plan document:

- `docs/dev/revised_runtime_first_refactor_plan_2026-05-15.md`

New priority:

```text
Phase 8.1 - Commander Integrated Chain Boundary
```

Next implementation rule:

- extract behavior-preserving runtime boundaries first
- do not tune trading behavior in the same patch

## Phase 8.1 Commander Integrated Chain Boundary - Slice 1

Started actual live intraday runtime modularization.

Active runtime path:

```text
scripts/run_session.py
-> libs/runtime/entrypoints/m13_live_loop.py
-> graphs/commander_runtime.py
```

Extracted integrated-chain support helpers into:

- `libs/runtime/commander/integrated_chain_support.py`

Moved out of direct inline commander runtime logic:

- integrated chain node loading
- intraday trade report emission helper
- repeated approved monitor-decision execution flow:
  - monitor intent -> decision packet
  - executor call
  - executor action/status extraction
  - intraday trade report emission
  - state update after execution

Design intent:

- create the first real boundary around the actual intraday integrated-chain path
- keep route behavior unchanged
- preserve `graphs.commander_runtime._run_integrated_chain` as the public test/runtime entry
- avoid any strategist/scanner/monitor tuning in this structural slice

Size impact:

```text
graphs/commander_runtime.py: 7113 -> 7109 lines
libs/runtime/commander/integrated_chain_support.py: 83 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\integrated_chain_support.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.3 Slice 1 - Strategist Cache Decision Boundary

Started Phase 8.3 with a larger responsibility-unit extraction instead of tiny helper slices.

Extracted strategist cache decision responsibilities into:

- `libs/runtime/commander/strategist_cache_decision.py`

Moved surfaces:

- strategist cache payload read
- cached strategist memory-context mismatch assessment
- cached strategist reuse preference assessment
- flat-position cached strategist reuse decision
- commander-skip cached strategist reuse decision

Design boundary:

- `graphs/commander_runtime.py` still orchestrates the runtime path.
- `libs/runtime/commander/strategist_cycle.py` still owns pre/post scanner strategist execution flow.
- `libs/runtime/commander/strategist_cache_decision.py` now owns whether cached strategist context is reusable.

Behavior target:

- no change to cache reuse semantics
- no change to reasons such as `commander_skip_cached_strategist`, `flat_position_cached_strategist`, `cached_memory_context_mismatch`
- no live restart after this slice because the market session was over

Size after slice:

```text
graphs/commander_runtime.py: 6230 lines
libs/runtime/commander/strategist_cache_decision.py: 318 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\strategist_cache_decision.py
```

Result:

```text
passed
```

Focused commander/strategist cache tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q
```

Result:

```text
81 passed
```

Runtime/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
23 passed
```

## Phase 8.4 Slice 1 - Monitor Exit Policy Config Boundary

Started Phase 8.4 with a larger responsibility-unit extraction.

Extracted monitor exit policy config resolution into:

- `libs/runtime/monitor_exit/policy_config.py`

Moved surfaces:

- exit policy config merge from strategy policy and applied policy
- applied monitor exit policy overrides
- flat backward-compatible exit policy aliases
- exit policy env overrides
- EOD flat nested policy resolution
- profit-protection defaults
- broker cost profile application for exit policy

Compatibility:

- `graphs/nodes/monitor_node.py` still uses `_resolve_exit_policy_config` as an import alias.
- Runtime field names and policy defaults remain unchanged.
- No live restart after this slice because the market session was over.

Size after slice:

```text
graphs/nodes/monitor_node.py: 6843 -> 6644 lines
libs/runtime/monitor_exit/policy_config.py: 185 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\policy_config.py
```

Result:

```text
passed
```

Focused monitor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
219 passed
```

Commander/monitor integration checks:

```text
venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_m21_commander_runtime_entry.py -q
```

Result:

```text
86 passed
```

Runtime/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
23 passed
```

## Phase 8.3 Slice 4 - Strategist Cache Store Boundary

Extracted strategist cache store/hydration responsibilities into:

- `libs/runtime/commander/strategist_cache_store.py`

Moved surfaces:

- strategist output contract normalization
- strategist output cache persistence
- strategist output cache hydration
- fallback hydration from `position_strategy_context`

Compatibility:

- `graphs/commander_runtime.py` still exposes `_normalize_strategist_output_contract`, `_persist_strategist_output_cache`, and `_hydrate_strategist_output_cache` through import aliases.
- Cache payload read and reuse decision remain in `strategist_cache_decision.py`.
- Runtime behavior and cache field names remain unchanged.

Size after slice:

```text
graphs/commander_runtime.py: 5489 lines
libs/runtime/commander/strategist_cache_store.py: 82 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\strategist_cache_store.py
```

Result:

```text
passed
```

Commander cache/store tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q
```

Result:

```text
81 passed
```

Post-scanner and strategist contract tests:

```text
venv\Scripts\python.exe -m pytest tests\test_commander_post_scanner_context.py tests\test_strategist_frame_llm_integration.py tests\test_strategist_explanation_contract.py -q
```

Result:

```text
43 passed
```

Runtime/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
23 passed
```

## Phase 8.3 Slice 3 - Strategist Refresh Decision Boundary

Extracted strategist refresh decision logic into:

- `libs/runtime/commander/strategist_refresh_decision.py`

Moved surfaces:

- pre-buy strategist refresh assessment
- selected-symbol tactical refresh decision
- cache freshness gate bypass for force signals
- refresh suppression when strategist input fingerprint is unchanged
- selected-symbol post-scanner refresh context construction

Compatibility:

- `graphs/commander_runtime.py` still exposes `_assess_pre_buy_strategist_refresh_need` and `_force_selected_symbol_tactical_refresh_decision` through import aliases.
- Runtime behavior and reason strings remain unchanged.

Size after slice:

```text
graphs/commander_runtime.py: 5555 lines
libs/runtime/commander/strategist_refresh_decision.py: 273 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\strategist_refresh_decision.py
```

Result:

```text
passed
```

Post-scanner and commander tests:

```text
venv\Scripts\python.exe -m pytest tests\test_commander_post_scanner_context.py tests\test_m21_commander_runtime_entry.py -q
```

Result:

```text
82 passed
```

Strategist refresh/report contract tests:

```text
venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py tests\test_strategist_explanation_contract.py -q
```

Result:

```text
42 passed
```

Runtime/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
23 passed
```

Strategist refresh/report contract tests:

```text
venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py tests\test_strategist_explanation_contract.py -q
```

Result:

```text
42 passed
```

## Phase 8.3 Slice 2 - Strategist Input Fingerprint Boundary

Extracted strategist input fingerprint and post-scanner context helpers into:

- `libs/runtime/commander/strategist_fingerprint.py`

Moved surfaces:

- post-scanner selected symbol resolution
- post-scanner candidate row compaction
- post-scanner candidate snapshot construction
- strategist input fingerprint construction
- fingerprint drift scoring
- cached strategist input drift assessment

Compatibility:

- `graphs/commander_runtime.py` still exposes the previous private helper names through import aliases where tests or internal callers use them.
- Runtime behavior and reason fields remain unchanged.

Size after slice:

```text
graphs/commander_runtime.py: 5794 lines
libs/runtime/commander/strategist_fingerprint.py: 491 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\strategist_fingerprint.py
```

Result:

```text
passed
```

Post-scanner and commander tests:

```text
venv\Scripts\python.exe -m pytest tests\test_commander_post_scanner_context.py tests\test_m21_commander_runtime_entry.py -q
```

Result:

```text
82 passed
```

Strategist refresh/report contract tests:

```text
venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py tests\test_strategist_explanation_contract.py -q
```

Result:

```text
42 passed
```

Runtime/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
23 passed
```

## Phase 8.1 Commander Integrated Chain Boundary - Slice 2

Continued actual live intraday runtime modularization.

Expanded:

- `libs/runtime/commander/integrated_chain_support.py`

Moved repeated shadow-runtime bookkeeping out of inline integrated-chain flow:

- strategist skipped/executed state updates
- strategist LLM-called detection
- strategist retry-count estimate extraction
- pre-buy refresh shadow fields
- post-scanner refresh shadow fields

Design intent:

- make future fast-path extraction smaller and less error-prone
- keep all existing `commander_shadow_runtime` field names and values stable
- avoid behavior tuning while extracting

Size impact:

```text
graphs/commander_runtime.py: 7109 -> 7054 lines
libs/runtime/commander/integrated_chain_support.py: 83 -> 159 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\integrated_chain_support.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.1 Commander Integrated Chain Boundary - Slice 3

Continued actual live intraday runtime modularization.

Expanded:

- `libs/runtime/commander/integrated_chain_support.py`

Moved the repeated monitor-decision execution path into:

- `run_monitor_decision_path`

Covered repeated flow:

- hydrate monitor symbol features
- run monitor node
- record `commander_shadow_runtime.monitor_decision`
- run decision node
- execute approved monitor decision
- update executor action/status shadow fields

Call sites converted:

- `integrated_chain_closeout_guard`
- `integrated_chain_monitor_only`
- normal integrated-chain final monitor pass

Design intent:

- reduce duplication before extracting whole fast-path branches
- preserve current monitor/decision/executor order
- keep behavior unchanged

Size impact:

```text
graphs/commander_runtime.py: 7054 -> 7046 lines
libs/runtime/commander/integrated_chain_support.py: 159 -> 188 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\integrated_chain_support.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.1 Commander Integrated Chain Boundary - Slice 4

Extracted the `integrated_chain_monitor_only` fast-path execution body into:

- `libs/runtime/commander/integrated_chain_support.py::run_monitor_only_fast_path`

The commander runtime still owns the decision of whether the fast path should run:

- `_should_use_monitor_only_fast_path`

Moved out of inline commander runtime flow:

- mark strategist as skipped for monitor-only path
- hydrate cached strategist output
- attach reporter feedback/applied policy
- build monitor-only commander decision
- select held-position focus symbol
- clear scanner output for monitor-only path
- emit monitor-only fast-path event
- run monitor/decision/execution path
- set final `path=integrated_chain_monitor_only`

Design intent:

- keep the fast-path condition local to commander runtime
- move the selected fast-path execution sequence into a focused support module
- preserve behavior and public state keys

Size impact:

```text
graphs/commander_runtime.py: 7046 -> 7028 lines
libs/runtime/commander/integrated_chain_support.py: 188 -> 247 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\integrated_chain_support.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.1 Commander Integrated Chain Boundary - Slice 5

Extracted the `integrated_chain_closeout_guard` fast-path execution body into:

- `libs/runtime/commander/integrated_chain_support.py::run_closeout_guard_fast_path`

The commander runtime still owns the decision of whether closeout guard should run:

- `_should_use_session_closeout_fast_path`

Moved out of inline commander runtime flow:

- closeout guard strategist skip bookkeeping
- cached strategist hydration
- reporter feedback/applied policy attachment
- closeout guard commander decision construction
- closeout account-order hydration
- pending buy cancel intent execution
- held-position focus symbol selection
- stage4 carry review invocation
- closeout guard monitor/decision/execution path
- final `path=integrated_chain_closeout_guard`

Design intent:

- keep the closeout guard condition local to commander runtime
- isolate the selected closeout guard execution sequence
- preserve pending-buy cancellation and carry-review behavior exactly

Size impact:

```text
graphs/commander_runtime.py: 7028 -> 6961 lines
libs/runtime/commander/integrated_chain_support.py: 247 -> 371 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\integrated_chain_support.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.1 Commander Integrated Chain Boundary - Slice 6

Split the growing integrated-chain support module by responsibility.

New modules:

- `libs/runtime/commander/nodes.py`
- `libs/runtime/commander/shadow_runtime.py`
- `libs/runtime/commander/execution.py`
- `libs/runtime/commander/fast_paths.py`

Changed:

- `libs/runtime/commander/integrated_chain_support.py` is now a compatibility export surface.

Responsibility split:

- `nodes.py`: lazy loading of integrated-chain graph nodes
- `shadow_runtime.py`: strategist/refresh shadow-runtime bookkeeping
- `execution.py`: intraday trade report emission and monitor-approved execution path
- `fast_paths.py`: monitor-only and closeout-guard fast-path execution sequences

Design intent:

- avoid creating a new large support file while shrinking `commander_runtime.py`
- keep stable helpers separate from fast-path orchestration
- preserve existing import compatibility during the transition

Size impact:

```text
libs/runtime/commander/fast_paths.py: 188 lines
libs/runtime/commander/execution.py: 82 lines
libs/runtime/commander/shadow_runtime.py: 78 lines
libs/runtime/commander/integrated_chain_support.py: 371 -> 37 lines
libs/runtime/commander/nodes.py: 33 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\integrated_chain_support.py libs\runtime\commander\nodes.py libs\runtime\commander\shadow_runtime.py libs\runtime\commander\execution.py libs\runtime\commander\fast_paths.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.1 Commander Integrated Chain Boundary - Slice 7

Extracted pre-scanner strategist cache/full-cycle preparation into:

- `libs/runtime/commander/strategist_cycle.py`

Moved out of inline commander runtime flow:

- cached strategist reuse resolution wrapper
- cached-frame shadow runtime setup
- pre-buy refresh shadow setup
- full-cycle strategist invocation setup
- market-change/repeated-context shadow fields
- strategist frame block handling wrapper
- strategist output cache persistence after full strategist run

Design intent:

- isolate strategist cache/full-cycle setup before scanner execution
- prepare for a later dedicated strategist call-control module
- preserve existing strategist call behavior and cache reuse behavior

Size impact:

```text
graphs/commander_runtime.py: 6961 -> 6956 lines
libs/runtime/commander/strategist_cycle.py: 68 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\strategist_cycle.py libs\runtime\commander\fast_paths.py libs\runtime\commander\execution.py libs\runtime\commander\shadow_runtime.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.1 Commander Integrated Chain Boundary - Slice 8

Extracted post-scanner strategist refresh handling into:

- `libs/runtime/commander/strategist_cycle.py::run_post_scanner_refresh_cycle`

Moved out of inline commander runtime flow:

- post-scanner refresh eligibility gate
- post-scanner commander decision construction
- tactical refresh decision override
- disabled-refresh shadow/event handling
- requested-refresh shadow/event handling
- strategist rerun after scanner
- strategist frame block handling after rerun
- strategist output cache persistence after rerun
- runtime fast-path payload after post-scanner refresh
- scanner rerun after strategist refresh
- suppressed-refresh shadow/event handling

Design intent:

- isolate the strategist re-call path that affects LLM cost
- keep behavior unchanged while making future call-control tuning safer
- keep scanner/strategist rerun ordering unchanged

Size impact:

```text
graphs/commander_runtime.py: 6956 -> 6872 lines
libs/runtime/commander/strategist_cycle.py: 68 -> 195 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\strategist_cycle.py libs\runtime\commander\shadow_runtime.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.1 Commander Integrated Chain Boundary - Slice 9

Extracted integrated-chain session setup helpers into:

- `libs/runtime/commander/session_context.py`

Moved out of inline commander runtime flow:

- shadow runtime prior-cache seeding
- prior strategist cache output extraction
- portfolio snapshot alignment
- portfolio preflight guard call
- risk context build
- initial integrated-chain commander decision construction

Design intent:

- keep runtime session context preparation separate from fast-path and strategist/scanner flow
- preserve lazy-loaded node monkeypatch behavior by passing node callbacks into the helper
- preserve portfolio preflight ordering

Size impact:

```text
graphs/commander_runtime.py: 6872 -> 6867 lines
libs/runtime/commander/session_context.py: 43 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\session_context.py libs\runtime\commander\strategist_cycle.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.1 Commander Integrated Chain Boundary - Slice 10

Extracted pre-entry exit sweep invocation into:

- `libs/runtime/commander/fast_paths.py::run_pre_entry_exit_sweep_if_needed`

Moved out of inline commander runtime flow:

- open-position guard around pre-entry exit sweep
- monitor-only reporter feedback/applied-policy setup before sweep
- `_run_pre_entry_exit_sweep` callback invocation
- `commander_shadow_runtime` refresh after sweep
- absent-later-stage LLM review recording when the sweep executes an exit

Design intent:

- keep the detailed sweep implementation in `commander_runtime.py` for now
- move the integrated-chain call-site ceremony out of the main session flow
- preserve existing pre-entry sweep behavior and state keys

Size impact:

```text
graphs/commander_runtime.py: 6867 -> 6868 lines
libs/runtime/commander/fast_paths.py: 188 -> 221 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\fast_paths.py libs\runtime\commander\integrated_chain_support.py
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 6.2 Daily Report Script Boundary Split

Extracted canonical daily report generation into:

- `libs/reporting/daily_report_generator.py`

Kept the script as a thin CLI/public compatibility wrapper:

- `scripts/generate_daily_report.py`

Updated library call sites:

- `libs/reporting/daily_report.py` now delegates to `libs.reporting.daily_report_generator`
- `libs/agent/reporter.py` now calls the daily report generator from `libs`, not `scripts`

Updated tests:

- daily report monkeypatches now target `libs.reporting.daily_report_generator`
- runtime boundary test now guards `libs/reporting/daily_report.py`, `libs/reporting/daily_report_generator.py`, and `libs/reporting/report_source_helpers.py` against direct `scripts.*` imports

Design intent:

- preserve existing script API and CLI output
- make the canonical daily report builder a reusable reporting module
- reduce `libs -> scripts` coupling without changing report schema or output paths

Behavior target:

- no change to daily report artifact paths
- no change to daily report JSON/Markdown schema
- no change to `Reporter.generate_daily_report` output contract

## Phase 6.2 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile libs\reporting\daily_report_generator.py libs\reporting\daily_report.py libs\agent\reporter.py scripts\generate_daily_report.py tests\test_daily_report.py
```

Result:

```text
passed
```

Focused daily/report tests:

```text
venv\Scripts\python.exe -m pytest tests\test_daily_report.py tests\test_reporter_script_wrappers.py tests\test_report_metadata_alignment.py tests\test_reporter_service.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
22 passed
```

## Phase 3.1 Pending Order Policy Extraction

Extracted unfilled order lifecycle policy decisions into:

- `libs/execution/order_lifecycle_policy.py`

Moved logic:

- fill/remaining quantity snapshot extraction from execution payloads
- eligibility decision for unfilled order recovery
- cancel reason selection for unfilled BUY/SELL
- post-cancel decision for BUY cancel completion
- post-cancel decision for SELL market replacement
- after-hours policy-required decision when regular session is closed

Executor still owns broker side effects:

- building cancel orders
- submitting cancel requests
- checking market clock
- building/submitting SELL market replacement orders
- normalizing broker responses

Design intent:

- keep irreversible broker calls in `execute_from_packet.py`
- keep lifecycle policy decisions in a narrow, side-effect-free module
- make future pending-order rules testable without touching broker execution code

Behavior target:

- no change to accepted order execution
- no change to unfilled BUY auto-cancel behavior
- no change to unfilled SELL cancel-then-market-replacement behavior
- no change to recovery reason strings

## Phase 3.1 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile graphs\nodes\execute_from_packet.py libs\execution\order_lifecycle_policy.py
```

Result:

```text
passed
```

Focused unfilled order tests:

```text
venv\Scripts\python.exe -m pytest tests\test_execute_from_packet.py::test_execute_from_packet_replaces_unfilled_sell_with_market_order tests\test_execute_from_packet.py::test_execute_from_packet_cancels_pending_unfilled_buy_without_market_replacement -q
```

Result:

```text
2 passed
```

Executor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_execute_from_packet.py tests\test_update_state_after_execution.py tests\test_order_client.py tests\test_real_executor_mock_mode_allowed.py tests\test_real_executor_disabled.py -q
```

Result:

```text
68 passed
```

## Phase 4.1 Truth Resolver Scaffold

Created the report truth resolver scaffold:

- `libs/reporting/trade_truth_resolver.py`

Integrated it into:

- `libs/reporting/report_truth_surface.py`

Moved logic:

- authoritative realized PnL availability decision
- fallback mark-only PnL percent handling
- ambiguous broker-day PnL observation-only handling
- authority/confidence/warning normalization scaffold

Current output policy:

- `truth_surface` field names are unchanged
- report markdown/summary behavior is unchanged
- Kiwoom day truth matching remains in `kiwoom_day_trade_truth.py`
- resolver currently wraps existing behavior so future MTS/API/split-fill basis work has a single target module

Design intent:

- keep truth precedence out of markdown rendering
- make MTS vs `ka10077` basis adjustments local to a resolver
- preserve current report output while introducing a clean extension point

Behavior target:

- no change to authoritative/fallback PnL labels
- no change to same-day summary PnL classification
- no change to Kiwoom split-fill aggregation behavior

## Phase 4.1 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile libs\reporting\trade_truth_resolver.py libs\reporting\report_truth_surface.py libs\reporting\kiwoom_day_trade_truth.py
```

Result:

```text
passed
```

Focused truth tests:

```text
venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py::test_build_deterministic_trade_report_adds_truth_surface tests\test_trade_report_ai.py::test_truth_surface_separates_broker_day_match_confidence_from_authority tests\test_trade_report_ai.py::test_truth_surface_hides_fallback_pct_from_realized_pnl_when_truth_unavailable tests\test_trade_report_ai.py::test_truth_surface_treats_ambiguous_broker_day_pct_as_observation_only tests\test_trade_summary_symbol_metadata.py::test_trade_summary_same_day_single_trade_prefers_current_truth_pct tests\test_kiwoom_day_trade_truth.py -q
```

Result:

```text
17 passed
```

Reporter truth bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py tests\test_broker_cost_profile.py tests\test_kiwoom_day_trade_truth.py -q
```

Result:

```text
147 passed
```

## Phase 5.1 Playbook Contract Inventory

Created the strategy playbook contract inventory:

- `libs/strategies/playbook_contracts.py`

Inventory now centralizes:

- playbooks: `breakout`, `pullback`, `reversal`, `defensive`
- scanner biases: `large_cap`, `leader`, `momentum`, `value`
- trade aggressiveness levels
- risk tones
- monitor guidance values
- market regime/sentiment values
- current tactical subtypes used by pullback evidence classification

Integrated into:

- `libs/strategies/contracts.py`

Design intent:

- stop duplicating strategist enum lists inside normalization code
- make future playbook/subtype additions start from one contract module
- keep runtime behavior unchanged while establishing the policy vocabulary boundary

Behavior target:

- no change to strategist output normalization
- no change to fallback defaults
- no change to scanner weighting or monitor interpretation

## Phase 5.1 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile libs\strategies\playbook_contracts.py libs\strategies\contracts.py graphs\nodes\strategist_node.py graphs\nodes\scanner_node.py
```

Result:

```text
passed
```

Inventory smoke:

```text
venv\Scripts\python.exe -c "from libs.strategies.playbook_contracts import playbook_inventory; import json; print(json.dumps(playbook_inventory(), ensure_ascii=False, sort_keys=True))"
```

Result:

```text
playbook inventory rendered successfully
```

Strategy/scanner contract tests:

```text
venv\Scripts\python.exe -m pytest tests\test_strategist_output_schema.py tests\test_strategy_policy_contract.py tests\test_scanner_strategy_frame_integration.py -q
```

Result:

```text
26 passed
```

Phase 5 bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_strategist_output_schema.py tests\test_strategy_policy_contract.py tests\test_scanner_strategy_frame_integration.py tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py -q
```

Result:

```text
36 passed
```

## Phase 5.2 Policy Bundle Normalization

Created the strategy policy bundle normalization layer:

- `libs/runtime/policy_bundle.py`

Moved/centralized logic:

- `strategy_policy.v1` schema default
- canonical strategy policy sections:
  - `market_policy`
  - `scanner_policy`
  - `entry_policy`
  - `monitor_policy`
  - `decision_policy`
  - `operator_explain`
- section dict normalization
- lightweight section availability/key summary

Integrated into:

- `libs/strategies/contracts.py`

Design intent:

- keep policy bundle shape stable outside strategist dataclass code
- make future policy consumers depend on one normalizer instead of ad hoc dict reads
- preserve existing dict output exactly for current callers

Behavior target:

- no change to strategist output schema
- no change to scanner/monitor policy selection
- no change to commander env migration behavior

## Phase 5.2 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile libs\runtime\policy_bundle.py libs\strategies\contracts.py graphs\nodes\strategist_node.py graphs\nodes\scanner_node.py graphs\nodes\monitor_node.py
```

Result:

```text
passed
```

Policy bundle smoke:

```text
venv\Scripts\python.exe -c "from libs.runtime.policy_bundle import normalize_strategy_policy_bundle, strategy_policy_bundle_summary; import json; p=normalize_strategy_policy_bundle({'market_policy': {'playbook': 'breakout'}, 'scanner_policy': None}); print(json.dumps({'bundle': p, 'summary': strategy_policy_bundle_summary(p)}, sort_keys=True))"
```

Result:

```text
policy bundle and summary rendered successfully
```

Phase 5 bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_strategist_output_schema.py tests\test_strategy_policy_contract.py tests\test_scanner_strategy_frame_integration.py tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py -q
```

Result:

```text
36 passed
```

Runtime/monitor boundary check:

```text
venv\Scripts\python.exe -m pytest tests\test_runtime_entrypoint_import_boundaries.py tests\test_intraday_monitor_signals.py tests\test_monitor_exit_guard.py -q
```

Result:

```text
181 passed
```

## Phase 4.2 Fill Aggregation Extraction

Extracted split-fill aggregation payload calculation into:

- `libs/reporting/trade_fill_aggregator.py`

Moved logic:

- split realized PnL summation
- split fee/tax summation
- aggregate PnL ratio calculation from buy basis and total quantity
- source row count preservation
- split-fill match payload shaping

Kept in `kiwoom_day_trade_truth.py`:

- Kiwoom day row lookup
- symbol/qty/price matching
- weighted sell-average split matching
- ambiguous repeated-symbol handling
- account profit row fallback

Design intent:

- keep fill arithmetic separate from broker-row matching
- make future MTS/API basis adjustments easier to test
- avoid changing report truth output fields

Behavior target:

- no change to split-fill match modes
- no change to realized PnL, fee, tax, or PnL ratio values
- no change to Kiwoom day truth authoritative behavior

## Phase 4.2 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile libs\reporting\trade_fill_aggregator.py libs\reporting\kiwoom_day_trade_truth.py libs\reporting\trade_truth_resolver.py
```

Result:

```text
passed
```

Focused split-fill tests:

```text
venv\Scripts\python.exe -m pytest tests\test_kiwoom_day_trade_truth.py::test_attach_broker_day_pnl_aggregates_split_rows_before_qty_fallback tests\test_kiwoom_day_trade_truth.py::test_attach_broker_day_pnl_aggregates_split_rows_by_weighted_sell_average -q
```

Result:

```text
2 passed
```

Fill aggregation/report bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_broker_trade_reconciliation.py tests\test_update_state_after_execution.py tests\test_trade_report_ai.py -q
```

Result:

```text
155 passed
```

Reporter truth bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py tests\test_broker_cost_profile.py tests\test_kiwoom_day_trade_truth.py -q
```

Result:

```text
147 passed
```

## Phase 3.2 Recent Order Guard Policy Extraction

Extracted recent order guard policy decisions into:

- `libs/execution/recent_order_guard.py`

Moved logic:

- expired recent-order record pruning
- recent duplicate BUY guard decision
- recent BUY settlement guard for structural SELL suppression
- recent duplicate/full SELL guard decision
- recent partial SELL remaining-quantity guard decision

Executor still owns process and persistence boundaries:

- recent guard path/env resolution
- JSON read/write
- order execution
- execution artifact/state updates

Design intent:

- keep duplicate-order protection rules in a side-effect-free module
- keep file persistence local to executor until a later storage-boundary cleanup
- make future guard rule changes testable without touching broker execution code

Behavior target:

- no change to duplicate BUY prevention
- no change to recent BUY partial-settlement SELL suppression
- no change to duplicate full SELL prevention
- no change to partial SELL remaining quantity behavior
- no change to guard reason strings

## Phase 3.2 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile graphs\nodes\execute_from_packet.py libs\execution\recent_order_guard.py libs\execution\order_lifecycle_policy.py
```

Result:

```text
passed
```

Focused recent order guard tests:

```text
venv\Scripts\python.exe -m pytest tests\test_execute_from_packet.py::test_execute_from_packet_blocks_recent_same_symbol_buy_before_position_reflects tests\test_execute_from_packet.py::test_execute_from_packet_blocks_structural_sell_while_recent_buy_is_partially_reflected tests\test_execute_from_packet.py::test_execute_from_packet_blocks_recent_full_sell_before_position_reflects tests\test_execute_from_packet.py::test_execute_from_packet_allows_recent_partial_sell_remaining_qty -q
```

Result:

```text
4 passed
```

Executor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_execute_from_packet.py tests\test_update_state_after_execution.py tests\test_order_client.py tests\test_real_executor_mock_mode_allowed.py tests\test_real_executor_disabled.py -q
```

Result:

```text
68 passed
```

## Phase 2.2 Entry Guard Blocker Extraction

Extracted Monitor entry guard/blocker decision logic into:

- `libs/runtime/monitor_entry_blockers.py`

Moved logic:

- same-symbol open-position block
- same-symbol pending-buy block
- max-position block
- closeout-window block
- post-exit cooldown block
- entry intent cooldown block
- entry quality gate block
- cost-adjusted edge block
- `failed_checks` and `primary_failure_axis` enrichment for quality/cost blocks

Monitor now calls `evaluate_entry_guard` and keeps the surrounding flow:

- build entry signal and cost/quality context
- evaluate guard result
- emit or suppress BUY intent
- pass the same blocker fields to no-trade, trade-story, and canonical artifact surfaces

Design intent:

- keep guard priority rules in one narrow module
- make future blocker additions local and testable
- keep `monitor_node.py` focused on orchestration rather than blocker taxonomy

Behavior target:

- no change to BUY blocking priority
- no change to guard reason strings
- no change to `failed_checks`, `primary_failure_axis`, or blocker surface inputs

## Phase 2.2 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_entry_blockers.py libs\runtime\monitor_entry_quality.py
```

Result:

```text
passed
```

Focused blocker/read-model tests:

```text
venv\Scripts\python.exe -m pytest tests\test_decision_observability.py tests\test_entry_blocker_read_model.py tests\test_trade_story_pipeline_enrichment.py -q
```

Result:

```text
46 passed
```

Focused entry/monitor tests:

```text
venv\Scripts\python.exe -m pytest tests\test_intraday_monitor_signals.py tests\test_chart_structure_features.py tests\test_monitor_exit_guard.py -q
```

Result:

```text
183 passed
```

Monitor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
219 passed
```

## Phase 2.1 Entry Quality Extraction

Extracted Monitor entry quality and pullback evidence classification into:

- `libs/runtime/monitor_entry_quality.py`

Moved logic:

- candidate source parsing
- candidate score/source breakdown lookup
- scanner chart-fit score snapshot
- entry quality gate
- VWAP reclaim pullback evidence subtype classification

Monitor now keeps only the entry flow:

- evaluate intraday entry signal
- evaluate cost/quality guards through imported helpers
- emit or block BUY intent
- attach the same `entry_quality_gate` and `pullback_evidence_profile` fields

Design intent:

- keep chart/quality scoring rules out of `monitor_node.py`
- make future entry quality tuning local to a narrow module
- avoid mixing candidate-quality rules with order-intent orchestration

Behavior target:

- no change to BUY intent behavior
- no change to entry quality gate field names
- no change to pullback evidence subtype field names
- no symbol-specific penalty added

## Phase 2.1 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_entry_quality.py
```

Result:

```text
passed
```

Focused entry quality tests:

```text
venv\Scripts\python.exe -m pytest tests\test_intraday_monitor_signals.py tests\test_chart_structure_features.py tests\test_monitor_exit_guard.py -q
```

Result:

```text
183 passed
```

Monitor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
219 passed
```

Syntax check:

```text
venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit_confirmation.py libs\runtime\exit_policy.py
```

Result:

```text
passed
```

## Phase 1.2 Started

Extracted Monitor exit policy-map assembly into:

- `libs/runtime/monitor_exit_inputs.py`

Monitor now keeps the runtime flow in place:

- resolve selected/price/position context
- build exit policy map through `build_monitor_exit_policy_map`
- call `evaluate_exit_policy`
- shape decision metadata

Behavior target:

- no change to trading behavior
- no change to exit policy field names
- no change to VWAP, cost-floor, position-entry-risk, ETF-deviation, or broker PnL crosscheck inputs

## Phase 1.2 Validation

Focused exit policy map tests:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
146 passed
```

Monitor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
219 passed
```

Syntax check:

```text
venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit_inputs.py libs\runtime\monitor_exit_confirmation.py libs\runtime\exit_policy.py
```

Result:

```text
passed
```

## Phase 1.2b Module Split

Refined the Phase 1.2 extraction to avoid creating a new mini-monolith.

New stable/extension layout:

- `libs/runtime/monitor_exit/policy_map_builder.py`
  - orchestration of exit-policy map enrichment
- `libs/runtime/monitor_exit/vwap_confirmation.py`
  - pure VWAP breakdown confirmation calculation
- `libs/runtime/monitor_exit/vwap_state_adapter.py`
  - state-backed VWAP helper facade
- `libs/runtime/monitor_exit/position_risk.py`
  - position entry-risk to exit-policy mapping
- `libs/runtime/monitor_exit/position_state_enrichment.py`
  - peak, partial-take, ladder, and position-state enrichment
- `libs/runtime/monitor_exit/market_enrichment.py`
  - quote, ETF deviation, VWAP, trend, signal, and resistance enrichment
- `libs/runtime/monitor_exit/adapters/state_data.py`
  - graph/state extraction adapter for quotes and minute rows
- `libs/runtime/monitor_exit/numeric.py`
  - stable numeric coercion helper

Compatibility facades remain:

- `libs/runtime/monitor_exit_inputs.py`
- `libs/runtime/monitor_exit_confirmation.py`

Design intent:

- stable pure calculations are separated from state adapters
- graph dependency is isolated to `monitor_exit/adapters/state_data.py`
- future exit-condition work should touch the narrow enrichment module, not `monitor_node.py`

## Phase 1.2b Validation

Focused exit tests:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
146 passed
```

Monitor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
219 passed
```

Dependency check:

```text
rg -n "from graphs\.nodes|import graphs\.nodes|skill_contracts" libs\runtime\monitor_exit libs\runtime\monitor_exit_inputs.py libs\runtime\monitor_exit_confirmation.py
```

Result:

```text
Only libs/runtime/monitor_exit/adapters/state_data.py imports graphs.nodes.skill_contracts.
```

## Phase 1.3 Observability Payload Split

Extracted Monitor exit observability/report payload shaping into:

- `libs/runtime/monitor_exit/observability.py`

Monitor now keeps only the runtime decision flow:

- resolve position and exit decision
- maintain pending-exit/confirmation state
- call `build_monitor_exit_payload`
- pass the payload to downstream trade-story and reporting hooks

Design intent:

- keep stable report field names away from hot-path orchestration
- make future report/diagnostic field additions local to the observability module
- avoid touching `monitor_node.py` for payload-only changes

Behavior target:

- no change to trading behavior
- no change to `monitor_exit` field names
- no change to sell guard, pending-exit lock, strategy-intent comparison, or trade-story enrichment inputs

## Phase 1.3 Validation

Syntax check:

```text
venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\runtime\monitor_exit\observability.py
```

Result:

```text
passed
```

Focused observability/exit tests:

```text
venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py::test_monitor_reason_human_marks_pending_exit_as_mismatch_not_trigger tests\test_monitor_exit_guard.py -q
```

Result:

```text
108 passed
```

Monitor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Result:

```text
219 passed
```

## Phase 8.2 Slice 1 - Commander Policy Surface Split

Actual intraday runtime priority remains:

```text
scripts/run_session.py --mode live --phase intraday --tick-pipeline integrated_chain
-> libs/runtime/entrypoints/m13_live_loop.py
-> graphs/pipelines/m13_live_loop.py
-> graphs/commander_runtime.py
```

Extracted commander runtime policy/type constants into:

- `libs/runtime/commander/policy_surface.py`

Moved surfaces:

- `RuntimeMode`, `RuntimePhase`
- pre-buy strategist refresh constants
- buy closeout cutoff default
- open-position strategist refresh cooldown
- commander-owned policy field lists
- entry-control blocker reason sets
- candidate-watch cascade default reason sets
- temporary commander runtime env defaults
- pre-entry exit sweep transient key list

`graphs/commander_runtime.py` now imports these values from the policy surface and keeps existing internal underscore names through aliases. This keeps behavior unchanged while moving stable policy definitions out of the large orchestration file.

Size after slice:

```text
graphs/commander_runtime.py: 6729 lines
libs/runtime/commander/policy_surface.py: 162 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\policy_surface.py
```

Result:

```text
passed
```

Focused entry/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
83 passed
```

Live runtime regression bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.2 Slice 8 - Commander Cooldown Policy Reader Split

Extended:

- `libs/runtime/commander/policy_readers.py`

Moved surface:

- commander cooldown policy resolution

The extracted helper only resolves:

- `resilience_policy.incident_threshold`
- `resilience_policy.cooldown_sec`
- env fallback `COMMANDER_INCIDENT_THRESHOLD`
- env fallback `COMMANDER_COOLDOWN_SEC`

Cooldown application, resilience mutation, and degrade-mode setting remain in `graphs/commander_runtime.py`.

Size after slice:

```text
graphs/commander_runtime.py: 6508 lines
libs/runtime/commander/policy_readers.py: 51 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\policy_readers.py
```

Result:

```text
passed
```

Focused entry/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
83 passed
```

Live runtime regression bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.2 Slice 7 - Commander Route Toggle Reader Split

Extended:

- `libs/runtime/commander/policy_readers.py`

Moved surface:

- commander route toggle resolution

Resolution order remains unchanged:

```text
applied_policy nested path -> state fallback key -> default
```

Size after slice:

```text
graphs/commander_runtime.py: 6514 lines
libs/runtime/commander/policy_readers.py: 38 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\policy_readers.py
```

Result:

```text
passed
```

Focused entry/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
83 passed
```

Live runtime regression bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.2 Slice 6 - Commander Policy Reader Split

Extracted small applied-policy reader utilities into:

- `libs/runtime/commander/policy_readers.py`

Moved surfaces:

- nested policy dict merge helper
- nested policy path value reader
- commander trade-report enabled reader

This keeps the large commander applied-policy builder in place but removes small stable read/merge primitives from the orchestration file.

Size after slice:

```text
graphs/commander_runtime.py: 6532 lines
libs/runtime/commander/policy_readers.py: 23 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\policy_readers.py
```

Result:

```text
passed
```

Focused entry/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
83 passed
```

Live runtime regression bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.2 Slice 5 - Reporter Feedback Route Policy Split

Extended:

- `libs/runtime/commander/route_surface.py`

Moved surface:

- commander reporter feedback policy resolution

This determines the advisory reporter feedback mode from selected route and runtime phase:

- closeout -> enabled
- monitor_only -> disabled
- cached_strategist -> disabled
- full_cycle -> auto
- fallback -> phase default auto

The large commander applied-policy builder remains in `graphs/commander_runtime.py` for now.

Size after slice:

```text
graphs/commander_runtime.py: 6544 lines
libs/runtime/commander/route_surface.py: 70 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\route_surface.py
```

Result:

```text
passed
```

Focused entry/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
83 passed
```

Live runtime regression bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.2 Slice 4 - Commander Route Surface Split

Extracted small route/config helpers into:

- `libs/runtime/commander/route_surface.py`

Moved surfaces:

- commander selected-route derivation
- reporter integration config normalization
- reporter hook request resolution

This intentionally does not move the large commander applied-policy builder yet. That builder still has broad dependencies and should be split in smaller behavior-preserving slices.

Size after slice:

```text
graphs/commander_runtime.py: 6574 lines
libs/runtime/commander/route_surface.py: 39 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\route_surface.py libs\runtime\commander\runtime_modes.py libs\runtime\commander\env_overrides.py libs\runtime\commander\policy_surface.py
```

Result:

```text
passed
```

Focused entry/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
83 passed
```

Live runtime regression bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.2 Slice 3 - Commander Runtime Mode Split

Extracted runtime mode/phase resolution into:

- `libs/runtime/commander/runtime_modes.py`

Moved surfaces:

- runtime mode normalization
- runtime phase normalization
- runtime transition normalization
- agent chain construction for runtime plan annotation
- runtime plan annotation
- `resolve_runtime_mode`
- `resolve_runtime_phase`

`graphs/commander_runtime.py` still exposes `resolve_runtime_mode` and `resolve_runtime_phase` through imports, preserving existing tests and external import behavior.

Size after slice:

```text
graphs/commander_runtime.py: 6605 lines
libs/runtime/commander/runtime_modes.py: 65 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\runtime_modes.py libs\runtime\commander\env_overrides.py libs\runtime\commander\policy_surface.py
```

Result:

```text
passed
```

Focused entry/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
83 passed
```

Live runtime regression bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```

## Phase 8.2 Slice 2 - Commander Env Override Split

Extracted commander runtime env override/default handling into:

- `libs/runtime/commander/env_overrides.py`

Moved surfaces:

- env boolean parsing
- commander temporary runtime env default apply/restore
- commander default bool resolution from temporary defaults
- post-scanner refresh enabled resolution
- pre-entry exit sweep enabled resolution
- commander memory usage disabled resolution

`graphs/commander_runtime.py` keeps the same internal helper names through import aliases, so existing call sites and behavior remain unchanged.

Size after slice:

```text
graphs/commander_runtime.py: 6670 lines
libs/runtime/commander/env_overrides.py: 73 lines
```

Validation:

```text
venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py libs\runtime\commander\env_overrides.py libs\runtime\commander\policy_surface.py
```

Result:

```text
passed
```

Focused entry/import boundary tests:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

Result:

```text
83 passed
```

Live runtime regression bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Result:

```text
102 passed
```
