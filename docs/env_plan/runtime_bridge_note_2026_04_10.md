# Env Plan Runtime Bridge Note 2026-04-10

## Purpose
This note connects the `docs/env_plan` phase track with the live runtime hotfix work that happened during validation.

The goal is simple:
- keep architecture/config ownership work clearly separated
- keep runtime safety hotfixes visible
- reduce confusion before Phase 6 begins

## What belongs to env-plan phases
The env-plan phases are primarily about **configuration ownership** and **architecture direction**.

Examples:
- env -> Commander/applied_policy ownership migration
- LLM execution profile migration
- model catalog layer creation
- profile-first selection design preparation

These phases answer:
- who owns configuration choice
- where canonical policy lives
- what future architecture boundary is intended

## What does not neatly belong inside env-plan phases
Recent live runtime hotfixes improved behavior, but they are not themselves env-plan milestones.

Examples:
- intraday trade report suppression
- report subprocess dedupe and cleanup
- ETF/ETN exclusion hardening
- exit observability alignment
- account PnL cross-check and anomaly handling

These changes answer:
- how we reduced live operational noise
- how we prevented unsafe or noisy runtime behavior
- how we made artifacts easier to explain

## Working classification
To keep future notes clearer, use this split:

### 1. Architecture / ownership work
Belongs in `docs/env_plan`

Examples:
- Commander owns toggle selection
- Commander owns numeric runtime parameters
- Commander owns LLM profile / execution profile selection

### 2. Runtime safety / hotfix work
Belongs in runtime or execution notes

Examples:
- live report subprocess suppression
- ETF buy blocking hardening
- exit trigger consistency fixes

### 3. Observability work
Can sit next to either track, but should be labeled explicitly

Examples:
- final exit thresholds surfaced in artifacts
- peak drawdown source surfaced
- policy source / profile source surfaced

## Practical rule for Phase 6
Phase 6 should begin as:
- profile interpretation
- selection planning
- observability only

Phase 6 should not absorb unrelated runtime hotfix work.

If live behavior needs a safety patch, document it as:
- runtime hotfix
- safety patch
- observability cleanup

not as implicit Phase 6 progress.

## Operator takeaway
If something changed in live behavior, do not assume it belongs to the next env-plan phase.

Check first whether it was:
1. architecture ownership work
2. runtime safety work
3. observability cleanup

That distinction will keep the next phases easier to reason about.
