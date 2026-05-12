# LLM Reports 4-Stage Summary Layout

Date: 2026-05-08
Status: Implementation started

## Goal

Keep the existing operator-facing Strategist summary stable while adding enough structure to see which Strategist LLM stage ran, which stage was skipped, and why.

## Runtime Layout

Existing path remains the primary summary:

```text
reports/llm/YYYY-MM-DD/<run_id>/strategist/
  prompt.json
  response.json
  meta.json
  strategist_summary.md
  strategist_summary.json
```

Stage-specific artifacts are added beside it:

```text
reports/llm/YYYY-MM-DD/<run_id>/strategist_stage1_market_frame/
reports/llm/YYYY-MM-DD/<run_id>/strategist_stage2_selected_symbol/
reports/llm/YYYY-MM-DD/<run_id>/strategist_stage3_hold_review/
reports/llm/YYYY-MM-DD/<run_id>/strategist_stage4_carry_review/
```

The run-level manifest is:

```text
reports/llm/YYYY-MM-DD/<run_id>/llm_stage_manifest.json
```

## Manifest Contract

Each manifest stage row should include:

```json
{
  "stage_index": 2,
  "stage_name": "selected_symbol_tactical_refresh",
  "call_kind": "selected_symbol_tactical_refresh",
  "component": "strategist_stage2_selected_symbol",
  "status": "ok",
  "reason": "selected_symbol_tactical_refresh",
  "prompt_ref": ".../prompt.json",
  "response_ref": ".../response.json",
  "meta_ref": ".../meta.json",
  "legacy_meta_ref": ".../strategist/meta.json",
  "strategist_summary_md_ref": ".../strategist/strategist_summary.md"
}
```

Skipped Stage 3/4 rows should use:

```json
{
  "stage_index": 3,
  "stage_name": "stale_intraday_hold_review",
  "call_kind": "stale_intraday_hold_review",
  "component": "strategist_stage3_hold_review",
  "status": "skipped",
  "reason": "no_open_position",
  "skip_reason": "no_open_position"
}
```

## Current Patch Boundary

Implemented now:

- Stage-specific artifact mirroring for Strategist LLM calls.
- `llm_stage_manifest.json` upsert helper.
- Stage 1 symbol-memory exclusion in compact Strategist LLM payloads.
- Stage 2 selected-symbol tactical refresh after Scanner selection when entry capacity exists.
- Stage 3 stale intraday hold review via the existing open-position refresh path when repeated HOLD/loss/carry-risk criteria request Strategist refresh.
- Stage 4 end-of-day carry review in session closeout guard and default closeout phase when held positions remain.
- Stage 3/4 skip manifest entries when no eligible LLM review was run.

Still deferred:

- A single combined markdown summary that renders all four stage rows into the existing `strategist_summary.md`.
- A separate lightweight model/profile for Stage 2/3/4 latency reduction.

## Reporting Policy

The daily/operator summary should stay concise:

- show the final applied frame,
- show whether Stage 2 ran or was explicitly skipped,
- show Stage 3/4 only as short status rows unless they actually ran,
- keep detailed prompt, response, memory, runner-up, and skip diagnostics inside `reports/llm`.
