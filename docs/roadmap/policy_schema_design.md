# Policy Schema Design

## 1. Purpose

This document turns the producer-side policy schema draft into a project baseline for the next phase of policy-aware monitor work.

The immediate goal is not to change trading behavior. The goal is to define a policy shape that Strategist and Commander can produce consistently so that Monitor can consume explicit policy fields before falling back to playbook- or threshold-driven inference.

In practical terms:

- `Phase 5-3` established the Monitor-side foundation
- this document defines the producer-side contract that feeds that foundation
- final decision ownership migration is explicitly out of scope here

## 2. Context from Phase 5-3

Phase `5-3` established the following monitor-side surfaces:

- `entry_policy_contract`
- `selected_policy`
- `selected_policy_schema`
- `policy_interpretation`
- `signal_evidence`
- `policy_interpreter_trace`
- `policy_alignment_summary`
- narrow `policy_aware_gating`

That work proved that the Monitor can behave like an explicit policy consumer. The remaining gap is producer-side shape quality.

Recent runtime observation showed:

- `selected_source` is usually `commander_applied_policy`
- `interpretation_basis` is still usually `fallback_playbook`
- `policy_schema_available` is still usually `false`

The main reason is structural: current `selected_policy` payloads are still much closer to numeric threshold policy than to interpretation-ready policy.

## 3. Design Goal

The design goal is to split producer policy into two layers inside `selected_policy`:

1. `interpretation_policy`
2. `threshold_policy`

This split exists to solve a real architectural mismatch.

- `interpretation_policy` carries intent, emphasis, and reading guidance
- `threshold_policy` carries numeric fallback and safety-oriented constraints

Without that split, Monitor keeps receiving a policy payload that is technically present but semantically closer to a threshold dict than to an interpretable policy object.

## 4. Why `selected_policy` Should Be Two-Layered

`selected_policy` should not be a single undifferentiated dict anymore.

If one object mixes:

- entry intent
- interpretation hints
- required/preferred checks
- numeric thresholds
- legacy safety values

then producer meaning and consumer behavior become hard to reason about.

The two-layer structure fixes that:

- `interpretation_policy` answers: "What should the Monitor prioritize when reading evidence?"
- `threshold_policy` answers: "What numeric or safety-oriented fallback controls still need to exist?"

This keeps the policy contract readable without removing conservative runtime protections.

## 5. Canonical Shape

The proposed canonical producer shape is:

```python
selected_policy = {
    "interpretation_policy": {
        "entry_style": str | None,
        "required_checks": list[str],
        "preferred_checks": list[str],
        "relaxable_checks": list[str],
        "blockers": list[str],
        "priority_hints": {
            "reclaim": str | None,
            "volume": str | None,
            "breakout": str | None,
            "pullback": str | None,
        },
        "evidence_focus": {
            "primary": list[str],
            "secondary": list[str],
        },
        "notes": list[str],
        "policy_adjustments": list[dict] | list[str],
    },
    "threshold_policy": {
        # Existing numeric threshold and fallback fields
    },

    # Backward compatibility:
    # existing top-level threshold fields may remain during migration.
}
```

## 6. `interpretation_policy` Role

`interpretation_policy` is the producer-side way to tell Monitor how to read the current setup.

It is not a decision override layer.
It is not a free-form recommendation blob.
It is not a replacement for evidence.

Its job is narrower:

- carry entry style intent
- identify required vs preferred vs relaxable checks
- identify blockers
- express signal priority hints
- point Monitor toward the most relevant evidence dimensions

This makes `interpretation_policy` an "intent + interpretation guidance" layer.

### 6.1 Field Intent

`entry_style`
- The intended entry posture or setup family.
- Examples: `breakout`, `pullback`, `reclaim`, `continuation`, `defensive`

`required_checks`
- Checks that should be treated as non-relaxable at the current producer posture.

`preferred_checks`
- Checks that strengthen alignment, explanation, and confidence but do not automatically become hard gates.

`relaxable_checks`
- Checks that may be eligible for narrow relaxation in tightly bounded future paths.

`blockers`
- Conditions that should be treated as strong reasons not to proceed.

`priority_hints`
- Relative emphasis hints for evidence axes such as reclaim, volume, breakout, and pullback.

`evidence_focus`
- Primary and secondary evidence dimensions the Monitor should pay attention to when building interpretation and trace surfaces.

`notes`
- Short policy notes, not long-form prose.

`policy_adjustments`
- Lightweight producer-side adjustment metadata for provenance and future auditability.

## 7. `threshold_policy` Role

`threshold_policy` preserves the numeric threshold and safety layer.

It should continue to support:

- legacy gate inputs
- conservative runtime fallback
- safety-oriented numeric controls
- gradual migration without abrupt behavior changes

This matters because the current roadmap is not removing legacy gates yet.

So the principle is:

- `interpretation_policy` improves policy readability
- `threshold_policy` preserves runtime safety and compatibility

## 8. Responsibility Split

### Strategist

Strategist is responsible for producing the initial policy proposal.

That includes:

- `interpretation_policy` derived from playbook, regime, posture, and setup intent
- `threshold_policy` derived from current numeric entry/monitor constraints

The initial producer implementation should remain deterministic rather than LLM-dependent.

### Commander

Commander is responsible for selecting, confirming, and carrying forward the applied policy.

That includes:

- selecting the effective source
- preserving provenance
- carrying `interpretation_policy` forward instead of collapsing back to threshold-only shape
- preserving `threshold_policy` as fallback safety input

### Monitor

Monitor is responsible for consuming policy, not inventing it.

That means:

- prefer `entry_policy_contract.selected_policy`
- prefer `interpretation_policy` over playbook inference
- use playbook/notes/rationale as fallback only when explicit fields are absent
- continue to use `threshold_policy` as a compatibility and safety layer

## 9. Backward Compatibility Rules

Backward compatibility is a hard requirement for this design.

The migration rules are:

1. `interpretation_policy` is additive
2. `threshold_policy` preserves existing numeric behavior
3. existing top-level threshold keys may remain during migration
4. Monitor must continue to work when `interpretation_policy` is absent
5. `fallback_playbook` remains valid until explicit policy content is broadly available

This keeps the transition safe while allowing explicit policy consumption to expand gradually.

## 10. Monitor Consumption Model

The intended consumption order is:

```text
entry_policy_contract.selected_policy
-> interpretation_policy
-> normalized policy schema candidate
-> policy_interpretation
-> evidence / trace / summary surfaces
-> legacy gates + narrow policy-aware integration
-> final BUY/WAIT
```

Important boundary:

> This document does not move final decision ownership away from legacy gates.

It only improves the shape of what Monitor receives from producer-side policy generation.

## 11. Non-Goals

This document does not define or authorize:

- final BUY/WAIT ownership migration
- broad policy-driven decision rollout
- threshold rewrite or threshold removal
- required-check bypass
- broad multi-gate relaxation
- free-form LLM policy generation
- execution-path changes

Those remain later-phase topics.

## 12. Why This Design Fits the Current Roadmap

This design fits naturally after `Phase 5-3`.

`Phase 5-3` established the Monitor-side foundation and proved that explicit policy consumption is structurally possible.

This document closes the producer-side gap by defining what Strategist and Commander should emit so that:

- Monitor can consume explicit policy fields more often
- `policy_schema_available` can move from mostly false toward real usage
- `interpretation_basis` can shift from mostly `fallback_playbook` toward `explicit_policy` or `mixed`

## 13. Natural Next Topics

The next documents or implementation phases that follow from this design are:

1. `Phase 5-3-2` chart structure feature design
   - extend the evidence vocabulary that `interpretation_policy` can reference
2. `Phase 5-4` ownership and wiring design
   - clarify how Strategist proposal and Commander applied policy become the canonical runtime source

Later, once the producer-side shape is stable, the project can address broader ownership transition and decision migration.

## 14. Summary

This document defines `selected_policy` as a two-layer producer contract:

- `interpretation_policy` for intent and interpretation guidance
- `threshold_policy` for numeric fallback and safety

That split lets Monitor move toward being an explicit policy consumer without forcing an unsafe or premature decision-ownership migration.
