# Reporter Commander Hooks (Phase 4)

## Purpose
Phase 4 adds structural integration points so Commander can call Reporter as a
subordinate analysis agent.

This phase does not promote Reporter into a decision-maker. Commander remains
the sole top-level orchestrator for runtime flow.

## Baseline authority split
Commander remains responsible for:
- runtime routing
- strategist/scanner/monitor/decision/executor sequencing
- trading path ownership

Reporter is limited to:
- analysis
- summaries
- report generation
- future strategist feedback packaging

Reporter must not:
- emit orders
- approve execution
- override guards
- override route selection
- override thresholds or risk controls

## Hook surface
The current structural hooks are:
- `maybe_generate_intraday_summary(...)`
- `maybe_generate_eod_reports(...)`
- `maybe_generate_strategist_feedback(...)`

These hooks are intentionally optional and disabled by default.

## Disabled-by-default policy
Commander runtime only invokes Reporter hooks when `state["reporter_integration"]`
is explicitly enabled.

Expected usage pattern:
- `enabled = false` or missing: no-op, no runtime behavior change
- `enabled = true`, `emit_reports = false`: reserved analysis hook only
- `enabled = true`, `emit_reports = true`: report generation only, still no
  execution authority

## Runtime semantics unchanged
This phase does not change:
- Monitor order prohibition
- Supervisor / Executor / Guard precedence
- approval / execution / risk semantics
- trading decision flow
- runtime thresholds or exit policy behavior

Reporter integration is observational only in this phase.

## Future extension point
`maybe_generate_strategist_feedback(...)` reserves the handoff point for future
Strategist consumption, but no Strategist integration is enforced yet.
