# Phase 5-4 — Ownership and Wiring Design

## 1. Background

Phase `5-3` established the policy-aware Monitor foundation.
Producer-side policy shape has been defined in `policy_schema_design.md`.
Chart-structure feature vocabulary has been defined in `phase_5_3_2_chart_structure_feature_catalog.md`.

What is still needed is not more decision logic first. What is needed is a clear ownership and wiring model.

Core statement:

> Phase `5-4` is not primarily a decision-expansion phase. It is the phase that fixes ownership and wiring first.

## 2. Current State (As-Is)

The current runtime structure is:

```text
policy sources
→ entry_policy_contract
→ selected_policy
→ selected_policy_schema
→ policy_interpretation
→ signal_evidence
→ policy_interpreter_trace
→ policy_alignment_summary
→ narrow policy_aware_gating
→ legacy gates
→ final BUY/WAIT
```

Current state summary:

- final BUY/WAIT ownership is still with legacy gates
- policy-aware layers already exist, but their role is mainly interpretation, explanation, and narrow integration
- producer-side explicit interpretation policy has been introduced conceptually, but full ownership migration has not happened yet

## 3. Target State (To-Be)

The target structure is:

```text
Strategist
→ interpretation_policy proposal
→ Commander
→ applied / selected policy contract
→ Monitor
→ policy_interpretation + signal_evidence + chart_structure_features
→ policy-aware decision
→ legacy threshold / gate as fallback safety
→ final BUY/WAIT
```

Target meaning:

- Strategist is the policy proposal owner
- Commander is the apply / provenance owner
- Monitor is the policy consumer and evidence interpreter
- legacy threshold / gate becomes the fallback safety boundary rather than the permanent primary owner

## 4. Ownership Definitions

### Strategist

Responsibilities:

- generate a policy proposal from market, playbook, regime, and setup context
- produce `interpretation_policy` and `threshold_policy` proposal content
- express trade idea and entry intent in policy form

Non-responsibilities:

- not the final execution decision owner
- not a direct order-intent emitter

### Commander

Responsibilities:

- determine `selected_source`
- determine `selected_policy`
- fix provenance
- confirm runtime route
- choose the canonical applied policy among multiple policy sources

Non-responsibilities:

- not the owner of micro signal evaluation
- not the owner of detailed monitor gate calculation

### Monitor

Responsibilities:

- consume selected / applied policy
- consume `signal_evidence`
- consume chart-structure features in future phases
- generate `policy_interpretation`, trace, and summary surfaces
- gradually increase policy-aware decision weight over time

Non-responsibilities:

- not the selector of policy source precedence
- not the generator of upstream policy

### Legacy Threshold / Gate

Responsibilities:

- remain the final safety and fallback owner in the current stage
- preserve conservative runtime behavior during migration
- act as the safety boundary while policy-driven wiring matures

Long-term direction:

- move from primary owner toward fallback safety

## 5. Wiring Direction

### Step A. Policy Producer Wiring

- Strategist produces `interpretation_policy` and `threshold_policy` proposal content
- Commander confirms the effective policy as selected / applied policy
- `entry_policy_contract` serves as the canonical handoff surface

This step is about policy creation and policy provenance, not Monitor logic.

### Step B. Policy Consumer Wiring

- Monitor uses `entry_policy_contract.selected_policy` as its primary input surface
- `interpretation_policy` is preferred
- `threshold_policy` remains the fallback safety input
- `playbook`, `notes`, and `rationale` are fallback-only interpretation aids

This step ensures Monitor behaves like a real policy consumer rather than a playbook-only interpreter.

### Step C. Feature Wiring

- low-level `signal_evidence` remains in place
- future `chart_structure_features` will be added as higher-level interpretation input
- `interpretation_policy` may reference those feature names and states

This lets the Monitor interpret both:

- low-level triggers
- higher-level market structure

without forcing threshold-only reasoning to do all the work.

### Step D. Decision Wiring

- current state: legacy gate remains primary
- migration direction: policy-aware decision weight expands gradually
- migration constraint: legacy gate remains active during transition

This means decision wiring evolves in stages rather than through a single ownership switch.

## 6. Migration Principles

The migration principles for `5-4` are:

- additive only
- behavior-preserving first
- no threshold removal before ownership migration is defined
- no ownership migration before producer / consumer contract stability
- no broad multi-gate relaxation before wiring is explicit

Core rule:

> Wiring and ownership come first. Decision migration comes later.

## 7. Future Position of Legacy Gate

Current position:

- final BUY/WAIT owner

Future position:

- fallback safety
- hard risk boundary
- compatibility layer

Important clarifications:

- legacy gates are not immediate removal targets
- they should remain until policy-driven decision behavior is stable enough
- the design direction is not to keep them as permanent primary owners forever

## 8. Connection to Phase 5-3-2

Phase `5-3-2` defines the feature vocabulary that lets Monitor interpret policy with more meaning.

Relationship summary:

- `reclaim`, `breakout`, `volume`, and `pullback` remain low-level signals
- structure, trend, support/resistance, and continuity features form the higher-level interpretation layer
- `5-4` wiring is what makes those two layers usable together under policy consumption

In other words:

- `5-3-2` defines what Monitor can talk about
- `5-4` defines how those signals become part of policy consumption and eventual decision ownership migration

## 9. Non-Goals

This document does not do the following:

- actually change the final decision owner
- remove thresholds
- introduce broad gating relaxation
- implement feature extractors
- implement runtime refactors
- wire UI consumers
- change the execution layer

This is an architecture design note, not a runtime change set.

## 10. Natural Next Steps

- build a chart-structure feature extractor skeleton
- design the next policy-aware decision migration slice
- define the legacy-gate fallbackization path
- expand producer policy richness
- plan env/config rename and deprecation work around scoring and legacy drift

## 11. Summary

Phase `5-4` exists to make runtime responsibility explicit.

The intended role split is:

- Strategist proposes policy
- Commander applies and fixes provenance
- Monitor consumes policy and evidence
- legacy gates remain as fallback safety during migration

That ownership model is the prerequisite for any later policy-driven decision migration.
