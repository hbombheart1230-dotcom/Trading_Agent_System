# Trade Report External Report Dependencies (2026-04-16)

## Goal

Identify which reports outside the core trade artifact chain are actually consumed by trade report generation.

This document excludes canonical run artifacts from the question.
The focus here is:

- which other report files are read by trade report code
- which ones are only linked for observability
- which ones are irrelevant to trade report generation

## Core Rule

For trade report purposes, the primary chain remains:

1. `reports/canonical/<day>/<run_id>/*.json`
2. `reports/trades/<day>/<trade_id>/lifecycle_bundle.json`
3. `reports/trades/<day>/<trade_id>/ai_trade_report_input.json`
4. `reports/trades/<day>/<trade_id>/reports/ai_trade_report.json`
5. `reports/trades/<day>/<trade_id>/reports/ai_trade_report.md`

Everything below is secondary to that chain.

## Directly Consumed By Trade Report

### `reports/dev/analysis/reporter_analysis`

Status:

- keep

Why:

- same-day reporter linkage reads this file
- `reporter_status_human` uses its summary/grade
- `ai_trade_report` sections such as reporter evaluation ultimately depend on it

Code evidence:

- `scripts/run_live_execution_bundle_report.py`
- `libs/reporting/single_trade_report.py`
- `libs/reporting/trade_story_pipeline.py`
- `libs/reporting/trade_report_ai.py`

Practical meaning:

- if this report disappears, trade report generation still runs
- but same-day linkage quality degrades
- reporter-related sections become weaker or missing

## Not Read For Trade Report Content, But Still Linked

### `reports/dev/analysis/trade_explain`

Status:

- keep for now
- not a direct trade report content dependency

Why:

- live bundle stores `trade_explain_json` / `trade_explain_md` in artifact metadata
- live bundle stores a small `trade_explain_summary`
- but trade report body generation does not currently read this report file as a content source

Important:

- this report is still used elsewhere by `reporter_feedback`
- so it is not safe to delete in the same slice

### `reports/daily/<day>/operator_summary.json|md`

Status:

- keep
- not a direct trade report content dependency

Why:

- live bundle stores `operator_summary_json` / `operator_summary_md` in artifact metadata
- current trade report body does not read operator summary content to build sections

Important:

- this report is still used by Operator UI overview and daily operator workflows

## Not Required By Trade Report Generation

### `reports/run_cards`

Status:

- disable by default
- manual-only generation is acceptable

Why:

- no direct trade report generation dependency found
- no same-day trade report section depends on its contents

### `reports/decision_story`

Status:

- disable by default
- manual-only generation is acceptable

Why:

- no direct trade report generation dependency found
- useful as auxiliary analysis, not required for trade report assembly

### `reports/live_summary`

Status:

- keep as runtime monitoring surface
- not a trade report dependency

Why:

- watch/monitoring use only
- trade report code does not consume it

### `reports/live_watch`

Status:

- keep as runtime monitoring surface
- not a trade report dependency

Why:

- watch/monitoring use only
- trade report code does not consume it

### `reports/metrics`

Status:

- keep for operator/daily health
- not a trade report dependency

Why:

- metrics feed operator summary and checks
- trade report generation path does not read metrics files directly

### `reports/daily/<day>/daily_report.json|md`

Status:

- keep for operator overview
- not a trade report dependency

Why:

- daily report is part of daily reporting surface
- trade report generation path does not use it directly

## Transitional Runtime Artifact

### `reports/dev/analysis/live_execution_bundles`

Status:

- keep for now
- reduce later after shared runtime service extraction

Why:

- current live intraday trade-report path still goes through `run_live_execution_bundle_report.py`
- this folder is part of that orchestration and regression surface
- trade report content does not depend on the day summary file under this folder
- but the current runtime flow still owns it

Practical meaning:

- do not prune this before live/batch shared-service parity is done

## Legacy / Fallback Surface

### `reports/operator_summary`

Status:

- legacy fallback
- remove after readers stop fallbacking to root-level path

Why:

- canonical path is now `reports/daily/<day>/operator_summary.json|md`
- some readers still fall back to root-level legacy location

## Action Plan By Report Family

### Keep as core

- `reports/canonical`
- `reports/trades`
- `reports/dev/analysis/reporter_analysis`

### Keep as operator/runtime surface

- `reports/daily`
- `reports/metrics`
- `reports/live_summary`
- `reports/live_watch`

### Keep temporarily, prune later

- `reports/dev/analysis/trade_explain`
- `reports/dev/analysis/live_execution_bundles`
- `reports/operator_summary` (legacy fallback only)

### Disable by default now

- `reports/run_cards`
- `reports/decision_story`

## Immediate Recommendation

If the goal is to reduce complexity without breaking trade report:

1. keep `reporter_analysis`
2. keep `trade_explain` for now
3. keep `live_execution_bundles` until shared runtime service extraction is complete
4. disable `run_cards` and `decision_story` by default
5. later remove legacy `reports/operator_summary` root fallback once readers are simplified
