# 2026-05-12 LLM report folder dedup and trade summary copy

## Issue

- Some LLM artifacts were written to both `reports/llm/<day>/<run_id>` and `reports/llm/<day>/trade_executed/<run_id>`.
- The common LLM run resolver preferred the flat date-root folder when both paths existed, so later report artifacts could continue writing to the stale flat folder.
- Trade bundles had `reports/strategist_llm_response.json`, but the human-readable `strategist_summary.md/json` was not copied into the same trade report bundle.

## Patch

- `find_llm_run_dir` now prefers classified run folders before the legacy flat date-root path.
- Trade-bundle LLM artifact persistence now uses the same classified-folder resolver instead of constructing `reports/llm/<day>/<run_id>` directly.
- `organize_llm_run` now merges a duplicate flat run folder into the classified target instead of leaving both folders in place.
- Duplicate file conflicts are preserved with `.root_duplicateN` suffixes; identical files are removed from the duplicate source during merge.
- `persist_trade_llm_artifacts` now copies `strategist_summary.md` and `strategist_summary.json` into the trade bundle `reports/` folder when summary refs exist.
- `_artifact_links.json` now exposes `strategist_summary_md` and `strategist_summary_json` links for the trade bundle.

## Backfill

- Merged `reports/llm/2026-05-12/2cc3426f0fcc471486845cbbe0e4af73` into `reports/llm/2026-05-12/trade_executed/2cc3426f0fcc471486845cbbe0e4af73`.
- Verified `2cc3426f0fcc471486845cbbe0e4af73` was a `000660` SELL run, not the `TRD_20260512_003060_05` trade anchor.
- Merged the actual `TRD_20260512_003060_05` strategy anchor run `189f6cdabc1945858315f736c2cf97eb` into `trade_executed`.
- Copied the matching `189f6...` strategist summaries into:
  - `reports/trades/2026-05-12/1300/TRD_20260512_003060_05/reports/strategist_summary.md`
  - `reports/trades/2026-05-12/1300/TRD_20260512_003060_05/reports/strategist_summary.json`
- Rewrote stale trade bundle LLM refs from flat paths to classified `trade_executed` paths.
- Ran the day organizer for `2026-05-12`; no hash run folders remain directly under `reports/llm/2026-05-12`.

## Verification

- `python -m pytest -q tests/test_canonical_artifact_validation.py tests/test_trade_bundle_persistence.py`
- Result: `17 passed`
- `py_compile` passed for:
  - `libs/runtime/llm_report_classifier.py`
  - `libs/runtime/canonical_artifacts.py`
  - `libs/reporting/trade_bundle_persistence.py`
  - `libs/reporting/llm_artifacts.py`
  - `libs/reporting/trade_bundle_state.py`

## Runtime Note

- The code path is fixed for future writes.
- The currently running live process will pick up code changes after the next restart; the current filesystem backfill has already been applied.
