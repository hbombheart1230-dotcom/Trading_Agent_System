# Strategist LLM Summary Artifact

Date: 2026-04-28

Status: implemented for deterministic rendering from stored strategist LLM `response.json`

## Purpose

The strategist LLM already writes structured interpretation into its `response.json`.

The summary artifact exists so an operator can inspect that interpretation quickly without opening the raw JSON. It is not a new LLM evaluation and it must not replace the canonical strategist artifact.

Canonical output path:

```text
reports/llm/<day>/<run_id>/strategist/strategist_summary.md
reports/llm/<day>/<run_id>/strategist/strategist_summary.json
```

Regeneration command:

```powershell
.\venv\Scripts\python.exe .\scripts\generate_strategist_llm_summary.py --response-json .\reports\llm\<day>\<run_id>\strategist\response.json
```

## Source Rule

The summary is deterministic.

- It reads existing strategist `response.json`.
- It does not call another LLM.
- It does not spend tokens.
- It does not invent a new strategy rationale.
- It may reorganize fields for readability.
- It may add deterministic operator audit notes, but those notes must be separated from strategist-authored output.

## Markdown Layout

### `전략가 원문 해석 출력`

This section is the primary section.

It renders strategist-authored fields first:

- `rationale`
- `strategy_adjustment_directives`
- `strategy_refresh_trace`
- `monitor_entry_policy`
- `strategy_horizon_feedback`

Meaning:

- `rationale`: why the strategist chose the frame
- `strategy_adjustment_directives`: what should be maintained, tightened, relaxed, rebalanced, or refreshed
- `strategy_refresh_trace`: 1st/base frame, 2nd/post-scanner refresh, and final application
- `monitor_entry_policy`: actual policy values handed to monitor
- `strategy_horizon_feedback`: horizon, hold window, exit guidance, invalidation, and monitor handoff

The report/UI should treat this section as the strategist's own interpretation surface.

### `운영자 검수 요약`

This section is deterministic audit.

It can highlight issues such as:

- `selected_themes` empty
- `available_themes` missing
- same playbook appearing in both best/worst memory
- symbol memory unavailable or gated
- missing handoff fields

It must not be confused with strategist-authored rationale.

## Relationship To AI Trade Report

`ai_trade_report.md` still consumes canonical structured strategist fields directly when available.

Authoritative fields for the trade report are:

- `strategy_thesis`
- `strategy_refresh_trace`
- `memory_usage_trace`
- `news_usage_trace`
- `scanner_handoff`
- `monitor_handoff`
- `trade_permission_frame`
- `responsibility_boundary`

Reporter rule:

- use these fields directly
- render or shorten them for readability
- do not reconstruct a different strategist rationale when they are present

The LLM summary artifact is an operator inspection artifact. It does not change the report contract.

## Current Example

Generated example:

```text
reports/llm/2026-04-28/eff2b0f2fa8a4f09a3193516232e4ba9/strategist/strategist_summary.md
reports/llm/2026-04-28/eff2b0f2fa8a4f09a3193516232e4ba9/strategist/strategist_summary.json
```

Current observed result:

- `playbook=defensive`
- `selected_themes=[]`
- `theme_selection_mode=fallback`
- root cause: `available_themes` was empty in the strategist response

This is expected for that historical run. It should change on the next fresh run if Commander supplies a live Kiwoom `theme_strength_packet` and `available_themes` before the strategist call.

## Validation

Validated on 2026-04-28:

```powershell
.\venv\Scripts\python.exe -m pytest .\tests\test_strategist_llm_summary.py .\tests\test_strategist_explanation_contract.py .\tests\test_trade_report_ai.py::test_ai_trade_report_compact_input_surfaces_structured_strategist_output_boundary .\tests\test_trade_report_ai.py::test_ai_trade_report_preserves_and_renders_structured_strategist_output .\tests\test_trade_report_ai.py::test_ai_trade_report_messages_use_clean_json_only_instructions -q
```

Result:

```text
7 passed
```

## Remaining Live Checks

Next market session should verify:

- Commander attaches theme policy before strategist invocation.
- Strategist response has non-empty `selected_themes` when Kiwoom theme data is available.
- `strategist_summary.md` shows the strategist-authored interpretation first.
- `ai_trade_report.md` renders structured strategist output without inventing separate rationale.
- `memory_usage_trace` and `news_usage_trace` are visible in canonical artifacts when available.
