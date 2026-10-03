# 2026-09-28 UEF-6 Formal Freeze

## Scope

Formally freezes UEF-6 (Dedup & Evidence Lineage): UEF-6A (Population Dedup Detection), UEF-6B (Direct
Evidence Lineage Sidecar), UEF-6C (Historical Dedup & Direct-Lineage Validation). Evaluation/reporting
integrity only -- no Scanner ranking, Strategist behavior, Commander approval, Monitor entry/exit rules,
position sizing, or broker execution is affected. UEF-6 is entirely read-only/additive against frozen
UEF-1..UEF-5.3.

## UEF-6A — Population Dedup Detection

- IMPLEMENTED: pure population-dedup classifier reusing the frozen UEF-1 identity model and
  `classify_duplicate_relation()` verbatim; distinguishes raw row / physical event / evaluation subject /
  evaluation record counts; order-independent multiset run identity.
- Codex audit (Evaluator Version Contract): an evaluator-version variant was wrongly counted inside a
  mixed duplicate group's excess total. Corrected: duplicate groups are sub-grouped by
  `(evaluation_record_id, evaluator_version)`.
- Codex audit (Order-Independent Run Identity): filesystem run identity used a raw byte hash, making it
  row-order sensitive. Corrected: rebased on a genuine order-independent MULTISET digest.
- APPROVED / COMPLETE. Checkpoint commit `ab699bb`.

## UEF-6B — Direct Evidence Lineage Sidecar

- IMPLEMENTED on the first delivery, approved without a correction round: a thin wrapper calling the
  frozen `aggregate_canonical_samples()` exactly once and returning both the unmodified `AggregateRecord`
  and a direct-evidence witness built from the same batches, cross-checked against the frozen aggregate's
  own persisted population counts.
- APPROVED / COMPLETE. Checkpoint commit `b1dbe5e`.

## UEF-6C — Historical Dedup & Direct-Lineage Validation

- IMPLEMENTED: Mode A (frozen-output UEF-6A observation) and Mode B (instrumented historical replay over
  an isolated, byte-verified snapshot, intercepting the frozen pipeline's own aggregation call point).
  Real Mode A run against target `UEF5RUN_bc1e299667c2ca94b977` reproduces the audited baseline exactly
  (107 raw / 80 events / 107 subjects / 107 records / 0 duplicates / 6 multi-evaluation events / 75
  LEGITIMATE_MULTI_HYPOTHESIS pairs). Real Mode B correctly fails closed `NOT_REPRODUCIBLE` for that same
  target: the historically recorded source sha256 for one discovered input artifact no longer matches its
  current bytes, and no authoritative exact-byte archive was found -- no lineage was fabricated, no
  approximate replay was accepted.
- Codex final audit found 4 concrete defects, all corrected:
  - (A) validation run identity was row-order sensitive across evaluator-version ties -- fixed with
    order-independent, multiplicity-sensitive full-content digests (`episode_population_semantic_digest`,
    `aggregate_population_semantic_digest`).
  - (B) `lineage_coverage.py` was missing from the UEF-6C semantic implementation digest -- added.
  - (C) witness↔aggregate accounting matched on `evaluation_record_id` alone, letting one witness falsely
    cover two context-different aggregates -- fixed with a full `(evaluation_record_id,
    canonical_aggregate_id, context_digest)` multiset match key plus an aggregate identity-consistency
    fail-closed check.
  - (D) duplicate-member historical totals conflated "distinct duplicated identity kinds" with "excess
    occurrence count" -- separated into two independently-sourced totals.
- APPROVED / COMPLETE. Checkpoint commit `657ddaa`.

## UEF-6 — Formal Freeze

- APPROVED and FORMALLY FROZEN by an independent Codex final closure audit: `CRITICAL 0, HIGH 0, MEDIUM 0,
  LOW 0`, `CORE_VERDICT: APPROVE_UEF6`, `UEF6_COMPLETE: YES`, `UEF6_FORMAL_FREEZE: YES`.
- Detail: [docs/research/uef6_dedup_evidence_lineage_freeze.md](../research/uef6_dedup_evidence_lineage_freeze.md).

## Verification (at freeze)

- Freeze manifest (UEF-1..3C): `11 / 11 MATCH`.
- UEF-5.1, UEF-5.2, UEF-5.3: unchanged (`git diff` clean against their frozen file sets).
- No UEF-6A or UEF-6B semantic file was changed during UEF-6C's closure or this freeze.
- Focused regression: UEF-6A 22 passed, UEF-6B 14 passed, UEF-6C 28 passed -- 64 passed, 0 failures.

## Governance

`docs/daily_patch/README.md`'s existing "When To Add An Entry" rule applies unchanged (formal freezes,
architecture decisions, production/runtime safety fixes, research-lifecycle changes, major incidents,
major roadmap changes -- not routine tests/refactors/formatting).

## Next

UEF-7 Alpha Board Normalization is NEXT. Not started by this closure.
