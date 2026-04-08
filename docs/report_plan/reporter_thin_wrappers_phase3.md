# Reporter Thin Wrappers (Phase 3)

## Purpose
Phase 3 reduces the report-generation scripts to thin wrappers.

The CLI entrypoints remain in place, but orchestration ownership now sits with
the Reporter service.

## Scope
Thin-wrapper treatment applies to the current primary report scripts:
- `scripts/generate_daily_report.py`
- `scripts/generate_metrics_report.py`
- `scripts/run_trade_explain_report.py`
- `scripts/run_run_card_report.py`
- `scripts/run_decision_story_report.py`
- `scripts/run_operator_daily_summary.py`

## What changed
Scripts now primarily do:
- argument or environment parsing
- Reporter service method selection
- result printing / exit handling

Existing report semantics remain in the underlying reporting modules and
generators.

## What did not change
- CLI compatibility is preserved
- output file names and paths stay the same
- freshness / provenance / narrative axis metadata stay the same
- runtime trading semantics remain unchanged
- `reports/trades/*` layout remains unchanged

## Why this matters
This gives the repo a single service boundary for deterministic reporting while
keeping the existing generators stable and reusable.

## Next step
Move additional internal consumers and remaining script entrypoints onto the
Reporter service boundary where that reduces duplication without changing
runtime behavior.
