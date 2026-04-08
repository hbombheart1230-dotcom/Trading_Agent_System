# Phase 6-2 Closeout: Internal Consumption and Routing Alignment

## Purpose
Phase 6-2 integrated read-model and separated reporting surfaces into strategist/reporting consumers and aligned model routing with the canonical policy-first, fallback-second approach.

## Implemented Scope
- Internal consumption:
  - Strategist/reporting consumers can read deterministic fact surfaces and report-oriented summaries.
  - Reporting pipelines preserve route provenance, policy surface summaries, and narrative-axis metadata for downstream consumers.
- Routing alignment:
  - Canonical env and policy-driven model selection are preferred.
  - Legacy model envs remain fallback-only for compatibility.
  - Route-related report aggregation now prefers commander canonical artifacts before any event fallback.
  - Route source and route provenance are surfaced explicitly in operator-facing reports.
- Report generation alignment added after the phase:
  - `daily_report` and `operator_summary` are generated independently from shared source helpers rather than reading each other's output files.
  - `trade_explain` uses the same route-source philosophy as metrics/daily/operator/run-cards/decision-story.
  - Freshness, stale, and source provenance metadata are surfaced explicitly.

## Fallback Policy
- Route facts:
  - primary source: commander canonical artifact
  - fallback source: event payload only when commander canonical artifact is missing
- Model routing:
  - canonical env or explicit override first
  - legacy env fallback second
  - final safe default last

## Runtime Semantics Unchanged
- Monitor must never place orders
- Execution layer approval / risk / guard semantics are unchanged
- Guard precedence is unchanged
- Reporting and logging remain observational only

## Remaining Limitations
- Some reports can still differ because they were generated at different times from a moving source window.
- Freshness and stale metadata now make those differences explicit rather than hiding them.
- Older runs may still require event fallback when commander canonical artifacts are missing.

## Current Status
Phase 6-2 is closed as the internal-consumption and routing-alignment baseline. Current follow-up work focuses on operational report quality, documentation clarity, and source/freshness consistency rather than semantic runtime changes.
