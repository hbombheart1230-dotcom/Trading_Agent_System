# 2026-05-13 Strategist Summary Stage Meta Rendering Fix

## Context

- `reports/llm/.../strategist/strategist_summary.md` showed broken Korean labels and many blank fields such as `model=-`.
- The same incomplete markdown was copied into the matching trade bundle under `reports/trades/.../reports/strategist_summary.md`.
- The affected run `070e298a57164b3ca7f6a500adbc9fb7` was actually a Stage 2 selected-symbol tactical refresh, but the summary renderer treated it like a Stage 1 market frame.

## Change

- `libs/reporting/strategist_llm_summary.py`
  - Loads sibling `meta.json` when `response.json` lacks model/status/stage fields.
  - Infers Stage 2/3/4 call kind from payload keys such as `selected_symbol_decision`, `hold_review_decision`, and `carry_review_decision`.
  - Renders Stage 2 selected-symbol outputs as a stage-specific report with target symbol, rank, runner-ups, monitor instruction, entry policy delta, actionability, confidence, and reason.
  - Replaces broken Korean markdown labels with readable Korean labels in the active renderer.
- `libs/reporting/llm_artifacts.py`
  - Persists stage metadata into prompt/response/meta artifacts.
  - Generates strategist summaries for `strategist_stage*` components, not only the legacy `strategist` component.

## Regenerated Artifacts

- `reports/llm/2026-05-13/trade_executed/070e298a57164b3ca7f6a500adbc9fb7/strategist/strategist_summary.md`
- `reports/llm/2026-05-13/trade_executed/070e298a57164b3ca7f6a500adbc9fb7/strategist/strategist_summary.json`
- `reports/llm/2026-05-13/trade_executed/070e298a57164b3ca7f6a500adbc9fb7/strategist_stage2_selected_symbol/strategist_summary.md`
- `reports/llm/2026-05-13/trade_executed/070e298a57164b3ca7f6a500adbc9fb7/strategist_stage2_selected_symbol/strategist_summary.json`
- Copied the fixed base strategist summary into `reports/trades/2026-05-13/1400/TRD_20260513_078890_01/reports/`.

## Validation

- `python -m py_compile libs/reporting/strategist_llm_summary.py libs/reporting/llm_artifacts.py`
- `python -m pytest tests/test_strategist_llm_summary.py -q`
- `python -m pytest tests/test_llm_status_semantics.py tests/test_strategist_llm_summary.py tests/test_canonical_artifact_validation.py tests/test_trade_bundle_persistence.py -q`

Result: `29 passed`.
