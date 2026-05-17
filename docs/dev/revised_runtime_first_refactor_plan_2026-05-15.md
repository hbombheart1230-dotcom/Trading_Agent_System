# Revised Runtime-First Refactor Plan - 2026-05-15

## Purpose

This document revises the incremental refactor order after confirming the currently running live session path.

The previous plan correctly identified reporting and mock-exam-day cleanup work, but the live intraday process currently runs through `scripts/run_session.py`, not directly through `mock_exam_day.py`. Therefore, the next priority is the actual intraday runtime path.

## Current Live Runtime Path

Observed process command:

```text
venv\Scripts\python.exe scripts\run_session.py --mode live --phase intraday --env-path .env --tick-pipeline integrated_chain --sleep-sec 30 ...
```

Effective dispatch path:

```text
scripts/run_session.py
-> libs/runtime/entrypoints/m13_live_loop.py
-> graphs/pipelines/m13_live_loop.py
-> graphs/pipelines/m13_tick.py
-> graphs/commander_runtime.py
-> integrated_chain
-> strategist_node / scanner_node / monitor_node / execute_from_packet
```

## Priority Rule

When the market is open or live intraday operation is active, prioritize modules on the actual runtime path before reporting-only or mock-exam-day orchestration cleanup.

Reporting and mock orchestration remain important, but they should not delay cleanup of the path that controls:

- strategist LLM call frequency
- scanner candidate selection
- monitor entry/exit decisions
- order execution handoff
- live-loop fast paths and cache reuse

## Completed Structural Work

### Phase 7 - Mock Exam Day Modularization

Status: mostly complete for the current goal.

Completed slices:

- Phase 7.3 - Mock exam day common/process split
- Phase 7.4 - Closeout backup liquidation split
- Phase 7.5 - Closeout phase orchestration split
- Phase 7.6 - Preopen/session phase orchestration split

Size result:

```text
libs/runtime/entrypoints/mock_exam_day.py: 1325 -> 258 lines
```

Remaining possible mock-exam-day cleanup:

- report rendering/writeout split
- parser/context builder split

These are lower priority than actual live intraday runtime cleanup.

## Phase 8 - Actual Intraday Runtime Modularization

This is the next workstream.

### Phase 8.1 - Commander Integrated Chain Boundary

Primary target:

- `graphs/commander_runtime.py`

Why:

- It is on the active live intraday path.
- It controls when strategist, scanner, monitor, and executor are called.
- It is currently a major hotspot at more than 7000 lines.

Initial extraction target:

- `libs/runtime/commander/integrated_chain.py`

Candidate responsibilities to move:

- integrated-chain execution body
- closeout guard routing
- monitor-only fast path
- pre-entry exit sweep
- cached strategist frame path
- post-scanner refresh path

Rules:

- Behavior-preserving extraction only.
- Keep existing public state keys unchanged.
- Keep event names and artifact fields unchanged.
- Preserve callback/dependency injection where tests depend on it.
- Do not tune strategist/scanner/monitor behavior in this phase.

Focused validation:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Restart policy:

- Restart live session after the focused tests pass.

### Phase 8.2 - Commander Runtime Policy Surface

Primary target:

- `graphs/commander_runtime.py`

Candidate extraction modules:

- `libs/runtime/commander/policy_fields.py`
- `libs/runtime/commander/runtime_modes.py`
- `libs/runtime/commander/env_overrides.py`

Candidate responsibilities to move:

- commander-owned policy field lists
- numeric/LLM policy field lists
- temporary runtime env defaults
- runtime mode and phase normalization
- route summary helpers

Goal:

- Isolate policy constants and normalization so future config changes do not require editing the large runtime orchestrator.

Focused validation:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_runtime_entrypoint_import_boundaries.py -q
```

### Phase 8.3 - Strategist Call Control Boundary

Primary targets:

- `graphs/commander_runtime.py`
- `graphs/nodes/strategist_node.py`

Candidate extraction module:

- `libs/runtime/commander/strategist_call_control.py`

Candidate responsibilities to move:

- strategist cache reuse decision
- pre-buy strategist refresh decision
- open-position strategist refresh cooldown
- post-scanner refresh trigger
- cache freshness/readiness threshold logic

Goal:

- Make strategist LLM call frequency understandable, testable, and adjustable without editing broad runtime orchestration.

Important:

- This phase may directly affect LLM call cost and runtime behavior. Start with extraction only, then tune behavior in a separate behavior patch if needed.

Focused validation:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_strategist_cache*.py tests\test_run_session.py -q
```

If no exact strategist-cache test file exists, add focused tests before behavior changes.

### Phase 8.4 - Monitor/Exit Runtime Boundary

Primary target:

- `graphs/nodes/monitor_node.py`

Candidate extraction modules:

- `libs/runtime/monitor_exit/*`
- `libs/runtime/monitor_entry/*`

Candidate responsibilities to continue moving:

- VWAP exit confirmation
- intraday position handling
- hold/exit confirmation state
- entry scoring attachment
- entry/exit observability payloads

Goal:

- Make premature exits and hold decisions easier to audit and patch.

Focused validation:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q
```

### Phase 8.5 - Scanner Candidate Selection Boundary

Primary target:

- `graphs/nodes/scanner_node.py`

Candidate extraction modules:

- `libs/runtime/scanner/candidate_selection.py`
- `libs/runtime/scanner/theme_scoring.py`
- `libs/runtime/scanner/market_representative_guard.py`

Candidate responsibilities to move:

- candidate pool scoring
- theme and turnover score attachment
- market representative guard
- candidate pool expansion
- Kiwoom condition input normalization

Goal:

- Make Samsung Electronics/SK Hynix concentration explainable by score components rather than by symbol-name penalties.

Focused validation:

```text
venv\Scripts\python.exe -m pytest tests\test_scanner*.py tests\test_m21_commander_runtime_entry.py -q
```

If scanner coverage is too sparse, add narrow characterization tests first.

## Phase 9 - Reporting Modularization

This replaces the previously proposed Phase 7.7-7.9 order. The work is still valid, but it moves after the actual intraday runtime workstream.

### Phase 9.1 - Daily Report Generator Modularization

Target:

- `libs/reporting/daily_report_generator.py`

Target modules:

- `libs/reporting/daily_report/freshness.py`
- `libs/reporting/daily_report/symbol_refresh.py`
- `libs/reporting/daily_report/markdown.py`
- `libs/reporting/daily_report/build_model.py`

Goal:

- Separate freshness checks, symbol refresh logic, markdown rendering, and report model construction.

Focused validation:

```text
venv\Scripts\python.exe -m pytest tests\test_daily_report.py tests\test_operator_summary_reports.py -q
```

### Phase 9.2 - Metrics Report Generator Modularization

Target:

- `libs/reporting/metrics_report_generator.py`

Target modules:

- `libs/reporting/metrics_report/event_extractors.py`
- `libs/reporting/metrics_report/aggregators.py`
- `libs/reporting/metrics_report/markdown.py`

Goal:

- Separate raw event extraction, aggregation, and rendering.

Focused validation:

```text
venv\Scripts\python.exe -m pytest tests\test_metrics*.py tests\test_operator_summary_reports.py -q
```

### Phase 9.3 - Large Reporting Hotspot Plan

Targets:

- `libs/reporting/trade_report_ai.py`
- `libs/reporting/trade_report_markdown_clean.py`
- `libs/reporting/trade_story_pipeline.py`

Rule:

- Do not start with broad edits.
- First create a decomposition map and test matrix.
- Then split by stable responsibility slices.

Likely decomposition themes:

- broker truth/read-model inputs
- symbol/theme metadata
- LLM prompt assembly
- markdown rendering
- post-sell tracking sections
- trade-story enrichment

Focused validation:

```text
venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py tests\test_trade_story_pipeline_enrichment.py tests\test_run_ai_trade_report_batch.py -q
```

## Phase 10 - Broad Regression and Live Restart Policy

Apply this after each completed workstream slice.

### For Phase 8.x

Required:

- focused runtime tests
- syntax check for touched modules
- live session restart
- stderr log size check

Recommended runtime checks:

```text
venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Restart command:

```text
scripts\restart_live_session.bat
```

### For Phase 9.x

Required:

- focused reporting tests
- report generation smoke test where feasible
- live restart only if runtime-imported modules changed

## Immediate Next Step

Start Phase 8.1:

```text
Commander Integrated Chain Boundary
```

First implementation rule:

- Extract only. Do not tune behavior in the same patch.
