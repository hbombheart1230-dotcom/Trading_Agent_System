# Operator UI Defer Note

## Purpose

- Record the current decision that `apps/operator_ui` is **not a near-term delivery surface**.
- Keep this as a planning note only; do not rewrite existing roadmap documents.
- Prevent future refactors from being driven by UI convenience when the primary near-term consumers are runtime, reporting, and batch/report pipelines.

## Current Decision

- Operator UI is **deferred for now**.
- We may revisit it much later, or it may remain unused depending on how the operating workflow settles.
- Because of that, we should avoid spending effort on UI polish, UI-specific abstractions, or front-end cleanup unless it is required for compatibility or to unblock non-UI work.

## Practical Meaning

- Do **not** use UI needs as the main reason to reshape runtime or reporting structures.
- Do **not** optimize for templates, route ergonomics, or detailed UI presentation right now.
- Keep UI-related code changes limited to:
  - compatibility preservation,
  - low-risk cleanup that helps non-UI consumers,
  - read-only separation that benefits reporting/batch usage first.

## How This Affects Phase 5-2

Phase 5-2 should still continue, but with a narrower interpretation:

- The main goal is **decoupling reporting read logic from UI-specific assembly**.
- The goal is **not** to invest in the UI as a product surface.
- `apps/operator_ui/data_access*` can remain as a compatibility layer for later use.
- `libs/reporting/*` read models and batch/report flows should be treated as the primary near-term consumers.

In practice, this means:

- Prefer moving pure read/normalize helpers into `libs/reporting`.
- Keep `apps/operator_ui/data_access_core.py` stable enough for future reuse, but do not over-design it around UI needs.
- Avoid large route/template/view-model cleanups unless they are directly needed for non-UI decoupling.

## What We Should Avoid Right Now

- UI feature work
- UI template redesign
- UI route reorganization
- front-end presentation cleanup
- UI-first view-model overengineering
- broad refactors done mainly to make the UI nicer

## What Is Still Worth Doing

- Reporting read-layer separation
- Removing `libs/reporting -> apps/operator_ui` coupling
- Keeping `apps/operator_ui.data_access` as a stable compatibility facade
- Small, safe extractions that reduce hidden coupling and help batch/report pipelines

## Revisit Trigger

Revisit the UI only when at least one of the following becomes true:

- Operator UI becomes a real operating surface again
- Reporting/read-model work is stable enough that a UI layer can be rebuilt on top cleanly
- Phase 5-3 policy ownership work is complete and downstream data contracts are more stable

Until then, assume:

- UI is deferred
- UI is not the primary customer
- Runtime/reporting correctness is more important than UI structure elegance

## One-Line Summary

For now, `apps/operator_ui` should be treated as a deferred compatibility surface, while reporting read-model separation and non-UI flows remain the primary focus.
