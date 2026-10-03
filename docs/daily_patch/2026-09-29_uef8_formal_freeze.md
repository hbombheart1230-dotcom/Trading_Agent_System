# 2026-09-29 UEF-8 Formal Freeze

## Scope

Formally freezes UEF-8 (Fair Comparison Validation). Evaluation/reporting integrity only -- no Scanner
ranking, Strategist behavior, Commander approval, Monitor entry/exit rules, position sizing, or broker
execution is affected. UEF-8 is entirely read-only against the frozen UEF-7 normalized Alpha Board.

## UEF-8 — Fair Comparison Validation

- IMPLEMENTED: pairwise `COMPARABLE`/`CONDITIONAL`/`NOT_COMPARABLE` fair-comparison validation over the
  frozen UEF-7 normalized Alpha Board -- full `N*(N-1)/2` pair conservation (91 pairs for the current
  14-candidate real board), canonical collision-safe pair identity (SHA-256 over an ordered structured
  payload, never delimiter concatenation), a fail-closed collision guard requiring pair count == unique
  pair ids == unique canonical pair tuples, deterministic hard-vs-conditional comparison rules (different
  question/horizon/cohort/no-shared-metric block outright; metric-availability mismatch, sample
  accounting, source overlap, and unproven population relation keep a pair conditional), and a core
  population-relation authority limitation: individual UEF-7 population proof never establishes a PAIR
  population relation, so `POPULATION_RELATION_NOT_PROVEN` is unconditional under the current UEF-7 schema
  and `COMPARABLE` is a reserved, currently-unreachable state. No ranking, scoring, promotion, or strategy
  change of any kind.
- Codex bounded correction (1 HIGH): individually-proven population statuses on both sides of a pair were
  wrongly treated as proving the pair's own population relation. Fixed by making
  `POPULATION_RELATION_NOT_PROVEN` unconditional -- a schema-contract property, not a today's-data
  observation.
- Codex bounded correction (1 HIGH): `comparison_pair_id` used delimiter-concatenated candidate ids,
  which could collide across adversarial candidate id shapes (e.g. `("A","B__C")` vs `("A__B","C")`).
  Fixed with a canonical SHA-256 digest plus a fail-closed uniqueness guard.
- APPROVED and FORMALLY FROZEN by an independent final closure audit: `CRITICAL 0, HIGH 0, MEDIUM 0, LOW
  0`, `CORE_VERDICT: APPROVE_UEF8`, `UEF8_COMPLETE: YES`, `UEF8_FORMAL_FREEZE: YES`,
  `COMPARABLE_REACHABLE_WITH_CURRENT_UEF7_SCHEMA: NO`. Checkpoint commit `b91d926`.
- Detail: [docs/research/uef8_fair_comparison_validation_freeze.md](../research/uef8_fair_comparison_validation_freeze.md).

## Verification (at freeze)

- Freeze manifest (UEF-1..3C): `11 / 11 MATCH`.
- UEF-5.1, UEF-5.2, UEF-5.3, UEF-6, UEF-7, and Alpha Board v2: unchanged (`git diff` clean against their
  frozen file sets).
- No UEF-8 semantic file was changed during this documentation/freeze task.
- Focused regression: UEF-8 41 passed, UEF-7 38 passed -- 79 passed, 0 failures.
- Real board (`through_day=2026-09-25`): 14 candidate rows, 91 pairs, 0 COMPARABLE / 7 CONDITIONAL / 84
  NOT_COMPARABLE, 91 unique pair ids, `POPULATION_RELATION_NOT_PROVEN=91` -- all derived dynamically, none
  hardcoded.

## Governance

`docs/daily_patch/README.md`'s existing "When To Add An Entry" rule applies unchanged (formal freezes,
architecture decisions, production/runtime safety fixes, research-lifecycle changes, major incidents,
major roadmap changes -- not routine tests/refactors/formatting).

## Next

UEF-9 Formal Evaluation Authority Freeze is NEXT. Not started by this closure.
