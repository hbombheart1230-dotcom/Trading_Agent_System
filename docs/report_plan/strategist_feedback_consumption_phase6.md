# Strategist Feedback Consumption (Phase 6)

## Purpose
This phase lets Strategist read `ReporterOutput.strategist_feedback_packet` as
optional advisory context.

The packet is not mandatory and does not override strategy logic.

## Rules
- feedback is optional
- feedback is advisory only
- controlled by runtime state/policy, not env
- default mode is `auto`
- no direct execution impact
- no threshold override

## Current behavior
When `reporter_feedback_mode=enabled`:
- Strategist reads `strategist_feedback_packet` from state if present
- the packet is exposed in strategist debug/output surfaces
- compact feedback may be added to LLM context

When `reporter_feedback_mode=disabled`:
- Strategist ignores the packet for reasoning purposes
- existing strategist behavior remains unchanged

When `reporter_feedback_mode=auto`:
- Strategist treats the packet as optional advisory context
- stale, missing, unavailable, or low-confidence packets are ignored
- fresh and relevant packets may be included in reasoning/debug surfaces

## Authority boundary
Reporter may provide:
- pattern summaries
- blocker analysis
- route distribution hints
- high-level recommendations

Reporter may not:
- force playbook changes
- force policy overrides
- force order behavior
- bypass approval / guard / risk controls

## Runtime semantics unchanged
This phase does not change:
- Monitor order prohibition
- Supervisor / Executor / Guard precedence
- approval / execution semantics
- monitor thresholds or exit policy
