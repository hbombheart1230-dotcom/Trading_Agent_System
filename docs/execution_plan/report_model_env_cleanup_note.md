# Report Model Env Cleanup Note

## Purpose

This note freezes the current operational meaning of report-related OpenRouter model environment variables after the alias cleanup pass.

The goal is to clarify which variables are primary, which aliases have been removed from active runtime selection, and which report surfaces remain deterministic.

## Current Runtime Mapping

### Primary model envs

These are the three model envs that currently map to distinct active report-generation paths.

1. `OPENROUTER_MODEL_TRADE_REPORT`
   - Used by AI trade report generation.
   - Primary code paths:
     - `libs/reporting/trade_report_ai.py`
     - `scripts/run_live_execution_bundle_report.py`

2. `OPENROUTER_MODEL_OPERATOR_UI`
   - Used by operator brief / intraday brief generation.
   - Primary code path:
     - `apps/operator_ui/data_access_core.py`

3. `OPENROUTER_MODEL_REPORTER_FINAL`
   - Used by reporter final AI review.
   - Primary code path:
     - `libs/reporting/reporter_ai_review.py`

### Removed alias envs

These env names are no longer part of active runtime model selection.

1. `OPENROUTER_MODEL_REPORTER_INTRADAY`
   - Former compatibility alias near `OPENROUTER_MODEL_OPERATOR_UI`
   - Removed from active runtime selection

2. `OPENROUTER_MODEL_DAILY_REPORT`
   - Former compatibility alias near `OPENROUTER_MODEL_REPORTER_FINAL`
   - Removed from active runtime selection

## Report Surface Mapping

### Trade report

- Path uses LLM model env directly.
- Primary env:
  - `OPENROUTER_MODEL_TRADE_REPORT`

### Operator brief / intraday brief

- Path uses LLM model env directly.
- Primary env:
  - `OPENROUTER_MODEL_OPERATOR_UI`

### Reporter final review

- Path uses LLM model env directly.
- Primary env:
  - `OPENROUTER_MODEL_REPORTER_FINAL`

### Daily report

- Canonical artifact path is currently deterministic.
- Current main path does not rely on a dedicated daily-report LLM model selection at runtime.
- Optional daily-report LLM usage now falls back to `REPORTER_FINAL` rather than a separate daily alias env.

### Symbol report

- Current path is deterministic.
- It reads linked artifacts such as trade report, operator brief, and lifecycle bundle.
- It does not currently use any of the OpenRouter model envs above as a direct model-selection input.

## Recommended Cleanup Direction

### Keep as primary knobs

Keep these as the explicit primary report-model envs:

- `OPENROUTER_MODEL_TRADE_REPORT`
- `OPENROUTER_MODEL_OPERATOR_UI`
- `OPENROUTER_MODEL_REPORTER_FINAL`

### Remove alias envs

These do not need to remain as separate env knobs:

- `OPENROUTER_MODEL_REPORTER_INTRADAY`
- `OPENROUTER_MODEL_DAILY_REPORT`

## Non-Goals

This note does not do any of the following:

- change runtime behavior
- rewrite router precedence beyond alias removal
- connect daily reports to a new LLM path
- change symbol report generation
- introduce new report-model env knobs

## Suggested Future Patch Scope

The cleanup direction is:

1. Keep three primary knobs
2. Remove alias envs from active runtime selection
3. Keep role compatibility where useful without preserving alias env names

## Bottom Line

The current system does not need five equally weighted report-model env knobs.

Operationally, the current structure is closer to:

- 3 primary envs
- 0 compatibility alias envs in active runtime selection

That is the contract this note freezes.
