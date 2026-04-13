# Profitability Recovery Day1 Diagnostics Close (2026-04-14)

## Scope
This phase did not change strategy, routing, sizing, or monitor entry/exit semantics.
The work focused only on diagnosability:
- holding-phase evidence richness
- same-day reporter linkage quality
- execution surface completeness
- daily validation / scorecard tooling

## What Changed
- Trade lifecycle generation now carries additive holding evidence fields:
  - `hold_duration`
  - `hold_duration_sec`
  - `holding_phase_summary`
  - `hold_events_count`
  - `monitor_context_snapshots`
  - `hold_signal_transitions`
  - `pre_exit_context_summary`
- Entry / exit / top-level lifecycle artifacts now surface `execution_details` with explicit keys, even when values are null.
- Same-day reporter linkage now has a robust fallback path:
  - direct lifecycle linkage if present
  - same-day reporter analysis artifact linkage if lifecycle linkage is absent
  - explicit linkage reason when linkage cannot be established
- Failure classification is attached additively:
  - `entry_failure`
  - `hold_failure`
  - `exit_failure`
  - `execution_failure`
  - `reporting_failure`

## Validation / Scorecard Tools
Added:
- `scripts/check_profitability_recovery_day1.py`
- `scripts/daily_profitability_scorecard.py`

These scripts verify or summarize:
- closed trade report generation regression
- closed trade `decision_only` misclassification
- holding evidence thin trades
- same-day linkage missing count
- execution field gaps
- top recurring diagnostic weakness

## Backward-Compatible Fallbacks
Many `2026-04-13` trade artifacts predated the new surfaces.
The Day1 diagnostic reader now uses safe fallback sources when direct fields are missing:
- `hold.json` for holding evidence
- `trade_outcome.holding_time` for hold duration
- same-day `reporter_analysis_YYYY-MM-DD.json` artifacts for linkage fallback
- lifecycle execution payloads for partial execution detail recovery
- `ai_trade_report_llm_response.json` and lifecycle diagnostics for closed-trade generation stability checks

## Current Interpretation Guidance
- `closed_trade_report_generation_regression = 0` means closed-trade AI report generation stayed stable.
- `same_day_linkage_missing = 0` means linkage is either direct or explicitly recovered through same-day reporter fallback.
- `holding_evidence_thin > 0` means some lifecycles still need richer hold snapshots, even though report generation is stable.
- `execution_fields_missing > 0` means diagnosability is still limited by incomplete order/execution fields in historical artifacts.

## Remaining Gaps
- Historical trades can still have thin hold evidence if only minimal hold snapshots were saved.
- Some execution fields, especially `order_id` and `avg_price`, still rely on partial legacy surfaces.
- This phase intentionally did not tune strategy or thresholds.

## Next Use
Use the new scorecard first.
Only after diagnostic gaps are visible and repeatable should we consider any strategy tuning.
