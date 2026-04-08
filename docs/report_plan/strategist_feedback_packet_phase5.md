# Strategist Feedback Packet (Phase 5)

## Purpose
This phase makes `ReporterOutput.strategist_feedback_packet` usable as an
optional input for Strategist.

The packet is analysis-only. It does not change trading runtime behavior and it
does not force Strategist consumption.

## Design rules
- deterministic first
- existing report layer reused
- minimal natural-language generation
- additive only

Reporter builds the packet from already-generated report surfaces such as:
- `metrics`
- `trade_explain`
- `daily_report`
- `operator_summary`

It does not introduce a new direct event parser for this phase.

## Current packet fields
- `insight_summary`
- `dominant_patterns`
- `blocker_analysis`
- `route_analysis`
- `recommendation`
- `confidence`
- `data_freshness`

Optional metadata:
- `available`
- `feedback_mode`
- `source_reports`
- `runtime_semantics_unchanged`

## Authority boundary
Reporter may describe patterns and recommendations.

Reporter may not:
- enforce strategy changes
- change route selection
- change thresholds
- emit orders
- bypass approval or guard logic

## Current integration status
- `ReporterOutput` now carries a usable deterministic packet
- Commander integration keeps this analysis optional
- Strategist consumption remains a future hook
