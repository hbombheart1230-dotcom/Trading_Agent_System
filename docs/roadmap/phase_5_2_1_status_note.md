# Phase 5-2-1 Status Note

## Purpose
This note freezes the current implementation scope of `5-2-1: Pre-buy strategist refresh`.
It is not a roadmap rewrite and it is not a Phase 5-3 policy document.

## Current Direction
The current design treats strategist refresh as a commander-owned orchestration decision.
The commander decides whether the next cycle should:
- reuse cached strategist context, or
- rebuild a fresh strategist frame.

Strategist remains responsible for gathering fresh context when a refresh is requested.
Monitor contributes observations, but it does not own refresh policy.

## What Is Implemented
The current implementation now supports these additive behaviors:
- commander can request `RUN_REFRESH`
- cache reuse follows commander intent instead of owning refresh policy itself
- refresh provenance is preserved through commander decision, strategist output, and commander artifact
- runtime shadow logging still records refresh path usage

Implemented refresh triggers currently include:
- near-entry transition became ready this cycle
- transition readiness score crossed the local threshold
- selected symbol is outside the cached strategist frame
- market regime shifted since cache generation

Implemented cache reuse preference currently includes:
- flat state
- cache available and within reuse window
- no forced refresh
- no commander-requested refresh

## What This Is Not
This is not a full policy system.
It does not:
- change strategist schema ownership
- change scanner schema ownership
- introduce commander applied-policy ownership for scanner/monitor behavior
- move scoring or threshold authority into strategist output

## Ownership Model
Current ownership is intentionally narrow:
- Commander: refresh / reuse routing decision
- Strategist: fresh news and context acquisition on refresh
- Scanner / Monitor: deterministic interpretation of the chosen frame

## Why This Still Belongs To 5-2-1
This work is still about invocation timing, stale cache avoidance, and provenance.
It is not yet about full policy ownership or agent contract redesign.
That later ownership work still belongs to Phase 5-3.

## Guardrails
Until 5-3:
- keep refresh logic local and additive
- avoid expanding this into a global policy schema
- avoid teaching scanner or monitor to reinterpret strategist intent directly
- prefer provenance and observability over new behavior

## Practical Read
If a cycle needs a new strategy frame, commander should request refresh.
If the cached frame is still valid, commander may prefer reuse.
That is the current implementation boundary.
