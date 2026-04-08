# Phase 6-1 Closeout: Read-Model and Fact/Narrative Separation

## Purpose
Phase 6-1 introduced deterministic read-model layers and separated fact payloads from narrative generation so that reports and downstream consumers could rely on stable, inspectable data structures.

## Implemented Scope
- Read-model layer:
  - Trade read-model and symbol read-model surfaces are implemented.
  - Daily/operator-facing report builders can consume deterministic fact payloads without depending on free-form narrative text.
- Fact/narrative separation:
  - Report builders keep fact payload generation separate from optional LLM narrative generation.
  - LLM-facing paths remain additive; deterministic facts are preserved even when AI review is skipped or unavailable.
- Reporting alignment added after the phase:
  - Narrative axis rules now make entry-first vs exit-first explanation ordering explicit.
  - Freshness metadata is attached to operator-facing reports so consumers can tell whether a report is fresh, stale, or empty.

## Operational Baseline
- Canonical artifact usage remains preferred for source facts.
- Narrative generation remains downstream of fact generation.
- Runtime semantics unchanged:
  - Monitor, Supervisor, Executor, and Guard semantics are unchanged
  - Approval and execution semantics are unchanged
  - Reporting remains observational only

## Remaining Limitations
- Some report fields are still limited by upstream event payload richness.
- Fact/narrative separation reduces ambiguity, but it does not guarantee that every downstream narrative section is equally detailed.
- Freshness metadata now helps explain timing differences between reports, but it does not eliminate timing differences caused by separate generation times.

## Current Status
Phase 6-1 is closed as the deterministic read-model and fact/narrative separation baseline. Current work mainly improves operational consistency, source provenance, and report clarity on top of that baseline.
