# Reporter Feedback Mode Ownership (Phase 7)

## Purpose
This phase moves `reporter_feedback_mode` ownership to Commander.

Strategist may still consume `strategist_feedback_packet`, but it is no longer
the owner of the mode that governs whether feedback should be considered.

## Canonical policy path
- `state["applied_policy"]["strategist"]["reporter_feedback_mode"]`

## Secondary compatibility paths
- `state["applied_policy"]["reporter_feedback_mode"]`
- `state["reporter_feedback_mode"]`

Compatibility paths remain advisory-only fallbacks. Commander-applied policy is
the preferred source of truth.

## Commander ownership rule
Commander chooses the mode from route/session context and injects it into
runtime state.

Current baseline:
- `full_cycle -> auto`
- `cached_strategist -> disabled`
- `monitor_only -> disabled`
- `closeout -> enabled`

These rules only control whether Reporter feedback may be considered as
advisory context. They do not alter thresholds, routes, approvals, or
execution behavior.

## Strategist responsibility
Strategist is a consumer only.

Strategist may:
- log the selected mode and source
- expose feedback in debug/decision-frame surfaces
- include compact feedback in optional LLM context
- apply `auto` gating based on packet freshness, confidence, and relevance

Strategist may not:
- own the final mode selection
- override strategy policy from feedback
- change thresholds, monitor rules, or execution behavior

## Runtime semantics unchanged
This phase does not change:
- Monitor order prohibition
- Supervisor / Executor / Guard precedence
- approval / execution semantics
- monitor thresholds
- strategy policy override rules
