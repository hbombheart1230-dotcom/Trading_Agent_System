# Reporter I/O Contracts (Phase 2)

## Purpose
This phase introduces thin `ReporterInput` and `ReporterOutput` contracts for the Reporter service.

The goal is not to replace the deterministic reporting core. The goal is to make the Reporter service boundary explicit so that future strategist feedback and commander integration can consume a stable interface.

## Scope
Phase 2 adds:
- `ReporterInput`
- `ReporterOutput`
- internal Reporter service wiring for the primary report surfaces

Phase 2 does not:
- rewrite `libs/reporting/*`
- change report JSON/MD semantics
- change runtime trading semantics
- change approval / guard / execution behavior

## ReporterInput
`ReporterInput` is intentionally thin and orchestration-focused.

Current baseline fields:
- `day`
- `reports_root`
- `canonical_report_root`
- `run_ids`
- `source_run_count`
- `latest_run_id`
- `latest_run_ts`
- `route_summary`
- `data_freshness`
- `available_surfaces`
- `narrative_axis_policy`
- `generation_mode`
- `flags`

The contract is metadata-oriented. It does not try to absorb the full report payload.

## ReporterOutput
`ReporterOutput` is a thin adapter around the existing report payloads.

Current baseline fields:
- `report_type`
- `output_paths`
- `generated_at`
- `data_freshness`
- `route_provenance`
- `narrative_axis_policy`
- `summary_metadata`
- `strategist_feedback_packet`
- `operator_packet`
- `success`
- `warnings`
- `payload`

`strategist_feedback_packet` is reserved for later phases and may be absent.

## Connected surfaces
Phase 2 connects these report methods first:
- `generate_daily_report(...)`
- `generate_operator_summary(...)`
- `generate_trade_explain(...)`

The same pattern is also applied to:
- `generate_metrics_report(...)`
- `generate_run_cards(...)`
- `generate_decision_story(...)`

## Runtime semantics unchanged
This phase is orchestration-only.

Unchanged:
- Monitor order prohibition
- Supervisor / Executor / Guard precedence
- approval / risk semantics
- `reports/trades/*` storage layout
- deterministic report generation behavior

## Next step
The next stage can use `ReporterOutput` as the handoff point for:
- strategist feedback packets
- commander report ownership
- thin script wrappers over Reporter service methods
