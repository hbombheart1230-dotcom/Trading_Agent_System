# Phase 6 Design Note: Profile-First Selection Architecture

## Purpose
Phase 6 is a design phase for Commander-centric LLM profile interpretation.

This note is intentionally non-runtime:
- no switching logic added
- no routing logic added
- no Commander integration implemented yet
- no Strategist/Reporter runtime reads added yet

## Core direction
Commander should choose **LLM profiles**, not raw model names.

The catalog layer introduced in Phase 5 gives Commander a structured way to
interpret candidate models through metadata instead of hardcoded string-only
selection.

## Intended architecture

### Commander chooses profile
Commander remains the configuration owner.

Commander should eventually emit something like:
- `applied_policy.llm.strategist.profile = balanced`
- `applied_policy.llm.reporter.intraday.profile = fast_free`
- `applied_policy.llm.reporter.daily.profile = strong_reasoning`

Phase 6 would extend that idea with a **selection plan** backed by model
catalog metadata.

### Catalog interprets candidate models
The catalog layer can help evaluate models through:
- `tags`
- `recommended_roles`
- `cost_tier`
- `latency_tier`
- `reliability`
- manual notes such as:
  - `json_stability_note`
  - `latency_note`
  - `cost_note`
  - `long_context_note`

### Initial scope: observability only
The first safe use of the catalog should be:
- selection planning
- profile candidate review
- recommended profile observability

Examples of safe outputs:
- "balanced profile candidate set"
- "preferred daily-review models"
- "fast low-cost intraday candidates"

This can be emitted as metadata or planning output without changing runtime
execution.

## What Phase 6 should not do yet
- no dynamic model switching in live runtime
- no direct model override from catalog metadata
- no automatic failover based on catalog tags alone
- no hidden routing changes behind Commander policy

## Suggested intermediate artifacts
Before runtime switching exists, Phase 6 can safely add:
- profile interpretation summary
- candidate model shortlist by role/profile
- reasons for shortlist selection using catalog metadata
- observability-only policy planning surfaces

Possible future examples:
- `commander_llm_selection_plan`
- `llm_profile_candidate_summary`
- `llm_profile_recommendation_trace`

These should remain advisory until a later switching phase is explicitly
approved.

## Separation of concerns
- Phase 5: data layer
- Phase 6: interpretation / planning layer
- Later phase: actual runtime switching

That separation is important because it keeps:
- catalog refresh safe
- Commander policy explainable
- runtime semantics stable

## Design checkpoint
Phase 6 should be considered successful if:
- Commander can interpret profiles through catalog metadata
- observability shows recommended candidate sets per profile
- runtime model selection still behaves exactly as before

Actual dynamic switching should remain a later, separately approved phase.
