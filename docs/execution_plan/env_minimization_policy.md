# Runtime Env Minimization Policy

## Purpose

This document freezes the forward policy for runtime environment variables.

The system is moving away from threshold-heavy, toggle-heavy runtime control.  
From this point forward, environment variables should be minimized and treated as deployment/runtime boundary configuration, not as the primary mechanism for strategy behavior tuning.

Core rule:

> Thresholds, feature toggles, and internal decision knobs should be owned by code and agent logic, not by user-managed env settings.

---

## Policy Statement

The preferred direction is:

1. keep env only where runtime deployment actually requires an external knob
2. move threshold / gate / on-off behavior into code-owned defaults
3. let the agent choose or adjust internal behavior from policy, runtime state, and evidence
4. remove unused or drifted envs incrementally during normal coding work

This is a control-surface minimization policy.

It is intended to reduce:

- configuration drift
- undocumented behavior differences across machines
- stale env knobs that no longer match current architecture
- operator burden for settings that should be internal

---

## What Env Is Still For

Environment variables remain acceptable only when they serve one of these roles:

### 1. Secrets and credentials

Examples:

- API keys
- broker credentials
- provider auth tokens

### 2. External integration endpoints

Examples:

- service base URLs
- provider endpoints
- explicit connector routing endpoints

### 3. Machine / deployment boundary configuration

Examples:

- filesystem roots
- explicit lock paths
- report output roots
- environment identity like dev/test/prod when truly needed

### 4. Hard operational safety rails that are truly deployment-owned

Examples may include:

- hard execution allow/deny mode
- real execution enablement
- approval mode

These should remain rare and clearly documented.

---

## What Env Is No Longer the Preferred Control Surface

The following categories should not be expanded through new env knobs unless there is a very strong exception.

### 1. Threshold tuning

Examples:

- score thresholds
- breakout / reclaim / extension cutoffs
- feature-specific sensitivity thresholds

Direction:

- keep in code-owned defaults
- expose through policy or runtime interpretation where appropriate
- let the agent choose behavior from context rather than operator env edits

### 2. Internal feature toggles

Examples:

- additive analysis flags
- shadow/explanation toggles
- narrow policy micro-slice switches
- strategy-path enable/disable flags that are only relevant to internal architecture migration

Direction:

- prefer code path ownership
- use staged rollout in code/tests/docs
- remove toggle once the slice is accepted

### 3. Policy behavior knobs

Examples:

- playbook-specific relaxations
- structure-aware decision hints
- style-specific required/preferred checks

Direction:

- own these through producer policy, monitor interpretation, and deterministic code
- do not require users to tune them via env

### 4. Architecture transition compatibility flags

Examples:

- legacy runtime allow flags
- temporary migration flags
- compatibility aliases kept after architecture has moved on

Direction:

- treat these as temporary
- deprecate aggressively
- remove once migration safety is confirmed

---

## Ownership Model

The intended ownership is:

- `env`
  - deployment boundary only
- `Strategist / Commander / Monitor code`
  - internal decision behavior
- `policy contract`
  - interpretation intent and runtime-consumable structure
- `agent/runtime`
  - adaptive selection and adjustment

This means:

- users should not be asked to hand-tune internal thresholds
- users should not need to flip internal migration toggles
- agents and code should carry the burden of choosing safe defaults and adapting behavior

---

## Default Rule for New Work

When adding a new capability, use this decision order:

1. Can this be encoded as deterministic code behavior?
   - If yes, do that.
2. Can this be expressed as policy contract or runtime evidence instead of env?
   - If yes, do that.
3. Is this truly deployment-specific or secret-bearing?
   - If yes, env is acceptable.
4. If none of the above are clearly true, do not introduce a new env knob by default.

In short:

> New envs require justification.  
> Internal behavior should justify itself in code first.

---

## Incremental Cleanup Rule During Future Coding

Future coding slices are allowed, and encouraged, to clean up envs incrementally.

When touching a subsystem, we should check whether related envs are:

- unused
- effectively dead switches
- compatibility leftovers
- renamed in practice but not in configuration surface
- still read but no longer appropriate as user-facing knobs

If one of those is true, the coding slice may also include:

1. removal of clearly unused env reads
2. alias removal when compatibility is no longer needed
3. deprecation of drifted names
4. migration of threshold/toggle semantics into code-owned defaults
5. documentation update for the reduced env surface

This should be done opportunistically, not postponed indefinitely.

---

## Safe Cleanup Guidelines

During incremental cleanup:

- do not change runtime behavior unintentionally
- preserve backward compatibility when the env is still actively used
- prefer deprecate -> observe -> remove when impact is non-trivial
- remove immediately only when the env is clearly dead or already replaced
- keep cleanup scoped to the subsystem being touched

This is not a license for broad config rewrites inside unrelated patches.

It is a license for disciplined, local cleanup when evidence is clear.

---

## Recommended Classification for Existing Env Reviews

Whenever we inventory envs, classify them into these groups:

### Keep

Use when the env is:

- deployment-owned
- secret-bearing
- externally required
- genuinely operational

### Keep but document better

Use when the env is still valid but:

- under-documented
- too implicit
- easy to misuse

### Deprecate

Use when the env:

- still works
- but no longer fits the target architecture

### Remove

Use when the env is:

- unused
- duplicated
- superseded by code-owned behavior
- superseded by another env or contract surface

### Rename only if truly necessary

Rename should be the exception, not the default.

If the behavior itself should move into code, removal is usually better than renaming.

---

## Connection to Current Architecture Direction

This policy matches the current roadmap direction:

- `5-3`
  - policy-aware monitor foundation
- `5-3-2`
  - chart-structure feature and structure-aware evidence expansion
- `5-4`
  - ownership and wiring clarification

Those phases all move behavior toward:

- policy contracts
- evidence surfaces
- deterministic runtime logic
- agent-owned adaptation

They do not move toward more operator-managed env knobs.

---

## Non-Goals

This document does not:

- delete envs by itself
- change runtime behavior by itself
- force immediate cleanup of all historical envs
- ban every env unconditionally

It defines the direction and the rule of engagement for future work.

---

## Practical Rule for Future Codex Work

When working on a subsystem:

1. check nearby env reads
2. decide whether each one is still justified
3. if unjustified and safe, remove it in the same slice
4. if removal is risky, mark it deprecated and document the next cleanup step
5. do not add a new threshold/toggle env unless it is clearly unavoidable

That should be the default working posture going forward.

---

## Bottom Line

The system should trend toward:

- fewer env knobs
- clearer deployment boundaries
- more code-owned behavior
- more policy-driven and agent-driven adaptation

The operator should manage the environment less.  
The system should manage itself more.
