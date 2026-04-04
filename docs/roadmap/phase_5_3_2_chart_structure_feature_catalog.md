# Phase 5-3-2 — Chart Structure Feature Catalog (Design)

## 1. Purpose

Phase `5-3-2` is the feature-vocabulary step for the policy-aware Monitor path.

The goal is not to add new decision logic yet. The goal is to define a stable evidence vocabulary that:

- `interpretation_policy` can reference
- future feature extractors can populate
- `signal_evidence` can expand toward
- Monitor can eventually use as a structure-aware consumer rather than a threshold-only consumer

One-line definition:

> A feature is not a condition. It is an interpretable signal unit that describes market state.

## 2. Design Intent

Current Monitor evidence is still centered on low-level signals such as:

- `reclaim`
- `breakout`
- `volume`
- `pullback`

Those signals remain useful, but they are closer to event- or trigger-level evidence.

Phase `5-3-2` extends the evidence vocabulary upward into higher-level market interpretation:

- price structure
- trend alignment
- support / resistance behavior
- continuity / momentum persistence

This gives `interpretation_policy` a richer and more stable language for expressing what the Monitor should care about.

## 3. Feature Layer Groups

The catalog is grouped into four feature layers.

### A. Structure

Features that describe the shape of price movement itself.

### B. Trend / Alignment

Features that describe directional alignment and moving-average posture.

### C. Support / Resistance

Features that describe interaction with important price levels.

### D. Continuity / Momentum

Features that describe whether a move is continuing, sustaining, or fading.

## 4. Feature Definition Format

Each feature in this catalog is defined using the same template:

- `name`
- `category`
- `description`
- `possible_states`
- `related_existing_signals`
- `interpretation_hint`

This keeps the vocabulary consistent across policy design, feature extraction, and future reporting/read-model surfaces.

## 5. Structure Features

### 5.1 `structure_hh_hl`

- `name`: `structure_hh_hl`
- `category`: `structure`
- `description`: Tracks whether higher-high / higher-low structure is being maintained.
- `possible_states`:
  - `intact`
  - `weakening`
  - `broken`
- `related_existing_signals`:
  - `breakout_ok`
  - `pullback_ok`
  - `reclaim_ok`
- `interpretation_hint`:
  - `intact` supports continuation-style or breakout-follow-through interpretations.
  - `weakening` suggests caution even when a local trigger is still present.
  - `broken` is a natural blocker candidate for long continuation logic.

### 5.2 `structure_range_compression`

- `name`: `structure_range_compression`
- `category`: `structure`
- `description`: Describes whether price is compressing into a tighter range or box.
- `possible_states`:
  - `none`
  - `moderate`
  - `tight`
- `related_existing_signals`:
  - `breakout_ok`
  - `volume_ok`
- `interpretation_hint`:
  - `tight` compression can support breakout-prep interpretation when paired with healthy volume context.
  - `none` means the setup should not be interpreted as a compression breakout.

### 5.3 `structure_breakout_attempt`

- `name`: `structure_breakout_attempt`
- `category`: `structure`
- `description`: Describes the current state of an attempted structural breakout.
- `possible_states`:
  - `none`
  - `forming`
  - `attempting`
  - `confirmed`
  - `rejected`
- `related_existing_signals`:
  - `breakout_ok`
  - `reclaim_gate_ok`
- `interpretation_hint`:
  - `confirmed` supports proactive continuation logic.
  - `rejected` should weigh against aggressive breakout entries even if a local trigger briefly fired.

## 6. Trend / Alignment Features

### 6.1 `ma_alignment_state`

- `name`: `ma_alignment_state`
- `category`: `trend_alignment`
- `description`: Describes moving-average alignment quality.
- `possible_states`:
  - `bullish`
  - `neutral`
  - `bearish`
  - `mixed`
- `related_existing_signals`:
  - no direct existing equivalent; this is a higher-level posture feature
- `interpretation_hint`:
  - `bullish` alignment supports continuation and pullback-long interpretation.
  - `mixed` means other evidence should carry more weight.

### 6.2 `ma_slope_strength`

- `name`: `ma_slope_strength`
- `category`: `trend_alignment`
- `description`: Describes the directional strength of trend slope rather than just ordering.
- `possible_states`:
  - `rising_strong`
  - `rising_weak`
  - `flat`
  - `falling_weak`
  - `falling_strong`
- `related_existing_signals`:
  - partially overlaps with `confidence` and trend-sensitive breakout interpretation
- `interpretation_hint`:
  - `rising_strong` supports follow-through interpretation.
  - `flat` or `falling_weak` is a warning against over-reading a local breakout.

### 6.3 `trend_regime`

- `name`: `trend_regime`
- `category`: `trend_alignment`
- `description`: Describes the broader trading regime rather than a single trigger condition.
- `possible_states`:
  - `trending`
  - `ranging`
  - `transition`
- `related_existing_signals`:
  - `breakout_ok`
  - `pullback_ok`
  - `reclaim_ok`
- `interpretation_hint`:
  - `trending` favors continuation and structured pullback logic.
  - `ranging` argues for more caution around breakout interpretation.
  - `transition` is especially relevant for policy notes and alignment summary.

## 7. Support / Resistance Features

### 7.1 `support_holding`

- `name`: `support_holding`
- `category`: `support_resistance`
- `description`: Describes whether an identified support level is holding or degrading.
- `possible_states`:
  - `holding`
  - `testing`
  - `lost`
- `related_existing_signals`:
  - `reclaim_ok`
  - `pullback_ok`
- `interpretation_hint`:
  - `holding` supports pullback and reclaim interpretations.
  - `lost` is a natural blocker candidate for long-biased entry logic.

### 7.2 `resistance_break_confirmed`

- `name`: `resistance_break_confirmed`
- `category`: `support_resistance`
- `description`: Describes whether a resistance break has actually held after the initial move.
- `possible_states`:
  - `none`
  - `attempting`
  - `confirmed`
  - `failed`
- `related_existing_signals`:
  - `breakout_ok`
  - `volume_ok`
- `interpretation_hint`:
  - `confirmed` is stronger than a plain breakout trigger because it includes post-break acceptance.
  - `failed` should weigh against continuation confidence.

### 7.3 `failed_breakout`

- `name`: `failed_breakout`
- `category`: `support_resistance`
- `description`: Captures whether an attempted breakout has reverted back below the relevant level.
- `possible_states`:
  - `none`
  - `suspected`
  - `confirmed`
- `related_existing_signals`:
  - `breakout_ok`
  - `reclaim_gate_ok`
- `interpretation_hint`:
  - `confirmed` is a strong blocker or invalidation hint for breakout-first policy posture.
  - This is especially useful as a higher-level explanation surface even before direct decision wiring.

## 8. Continuity / Momentum Features

### 8.1 `momentum_follow_through`

- `name`: `momentum_follow_through`
- `category`: `continuity_momentum`
- `description`: Describes whether a move continues after the initial trigger or breakout.
- `possible_states`:
  - `strong`
  - `moderate`
  - `weak`
  - `none`
- `related_existing_signals`:
  - `breakout_ok`
  - `confidence_ok`
- `interpretation_hint`:
  - `strong` supports continuation bias and post-break confidence.
  - `weak` suggests the move exists but is not proving itself.

### 8.2 `volume_sustain`

- `name`: `volume_sustain`
- `category`: `continuity_momentum`
- `description`: Describes whether volume participation remains supportive after the initial setup.
- `possible_states`:
  - `strong`
  - `adequate`
  - `fading`
  - `absent`
- `related_existing_signals`:
  - `volume_ok`
- `interpretation_hint`:
  - `strong` or `adequate` supports breakout and continuation credibility.
  - `fading` or `absent` weakens the meaning of an otherwise valid structural trigger.

### 8.3 `momentum_decay`

- `name`: `momentum_decay`
- `category`: `continuity_momentum`
- `description`: Describes whether the move is losing force after entry-style conditions appear.
- `possible_states`:
  - `none`
  - `mild`
  - `strong`
- `related_existing_signals`:
  - partially overlaps with low-confidence or post-break weakness, but operates as a higher-level interpretation feature
- `interpretation_hint`:
  - `strong` decay is a natural blocker or caution feature even if the original trigger looked valid.
  - `none` supports clean follow-through interpretation.

## 9. Relationship to Existing Signals

Existing signals remain valid:

- `reclaim`
- `breakout`
- `volume`
- `pullback`

But under this design they should be treated as lower-level signal units.

The new structure/trend/support/continuity features are higher-level interpretation features that sit above those low-level checks.

In other words:

- low-level signals answer: "Did this local event happen?"
- higher-level features answer: "What does the broader setup mean?"

That split is important for future Monitor design because it prevents threshold logic from doing all the interpretive work by itself.

## 10. Interpretation Policy Integration Examples

These examples are illustrative design targets, not runtime wiring.

### Example A: Breakout continuation posture

```text
required_checks:
  - breakout_ok
  - volume_ok

preferred_checks:
  - structure_hh_hl=intact
  - momentum_follow_through=strong
  - resistance_break_confirmed=confirmed

blockers:
  - failed_breakout=confirmed
  - momentum_decay=strong
```

### Example B: Pullback reclaim posture

```text
required_checks:
  - pullback_ok

preferred_checks:
  - support_holding=holding
  - ma_alignment_state=bullish
  - trend_regime=trending

blockers:
  - structure_hh_hl=broken
  - support_holding=lost
```

### Example C: Defensive transition posture

```text
required_checks:
  - confidence_ok

preferred_checks:
  - trend_regime=transition
  - structure_range_compression=moderate

blockers:
  - failed_breakout=confirmed
  - momentum_decay=strong
```

## 11. Naming Rules

The naming rules for this catalog are:

- use `snake_case`
- prefer stateful enum/string values over booleans
- keep names aligned with existing signal vocabulary where possible
- avoid introducing opaque model-specific terminology
- keep feature names descriptive enough to be used in policy, trace, and reporting surfaces

Preferred pattern:

- feature name is stable
- state carries meaning

Example:

- preferred: `trend_regime = "transition"`
- less preferred: `is_transition = true`

## 12. Non-Goals

This document does not define:

- feature extractor implementation
- threshold definitions
- decision logic wiring
- additional scoring frameworks
- LLM-generated feature extraction

This is a vocabulary and grouping document only.

## 13. Next-Step Connection

After this catalog, the natural follow-up steps are:

### After `5-3-2`

- build a feature-extractor skeleton that can populate the catalog fields deterministically

### In `5-4`

- wire `interpretation_policy` so it can reference these features as part of explicit policy consumption

Longer term, these features can support:

- richer `policy_interpreter_trace`
- more meaningful `policy_alignment_summary`
- clearer separation between trigger detection and market-state interpretation

## 14. Summary

This catalog defines the first chart-structure-oriented evidence vocabulary for the policy-aware Monitor path.

It expands the evidence language from low-level trigger signals toward higher-level market interpretation across four layers:

- structure
- trend / alignment
- support / resistance
- continuity / momentum

That gives future `interpretation_policy` and feature-extractor work a stable naming baseline without changing runtime behavior today.
