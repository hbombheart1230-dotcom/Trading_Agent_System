# 2026-09-28 UEF-5.3 Formal Freeze

## Scope

Formally freezes UEF-5.3 (Historical Dual Run). Evaluation/reporting integrity only -- no Scanner
ranking, Strategist behavior, Commander approval, Monitor entry/exit rules, position sizing, or broker
execution is affected. UEF-5.3 is entirely read-only against frozen UEF-1..UEF-5.2 and the live
repository's own evaluation output.

## UEF-5.3 — Historical Dual Run

- IMPLEMENTED: legacy↔canonical family mapping (Q10 Semiconductor, Q12 Calc1, Q11 v2 EXIT), a
  dual-run comparison core (canonical run reader, legacy readers, divergence classifier, reporter), and
  the bounded divergence-reason taxonomy.
- Codex audit (Core Correction 1): the real canonical UEF-3A metric contract was misread and MDD was
  never compared; input/canonical/run identity was incomplete; canonical-only cells were silently
  dropped from accounting. Corrected.
- Codex re-audit (Core Correction 2): a non-comparable metric could suppress a comparable one; evidence
  identity did not cover canonical content or reader implementation; `HASH_MISMATCH` could still report
  `EXACT_SAME_SOURCE`; Q12 Calc1's first matching legacy view silently consumed the canonical aggregate;
  an absent aggregate plus a legacy zero count was wrongly `EXACT_EMPTY`. Corrected.
- Source-alignment micro-fix: decoupled `source_alignment` (same proven source evidence?) from the
  numeric comparison result -- a proven-same-source unit can legitimately diverge.
- Final Closure Fix: Q12 Calc1 still allowed metric comparison from count equality alone; per-metric
  comparison results were computed but never persisted to the output record. Corrected: comparison now
  gated on a positive population-identity proof, and every record persists a structured
  `metric_comparisons` map.
- Final one-item audit: the population-identity proof trusted a serialized `lineage_status=="FULL"`
  label without structurally re-verifying it, and did not require legacy↔canonical member-ID equality.
  Corrected: independent structural re-verification of the frozen record contract's own lineage
  invariant, plus exact legacy/canonical member-ID set equality -- no membership ever reconstructed or
  invented.
- APPROVED and FORMALLY FROZEN by an independent Codex final closure audit: `CRITICAL 0, HIGH 0, MEDIUM
  0, LOW 0`, `CORE_VERDICT: APPROVE_CORE`, `UEF5_3_COMPLETE: YES`. One non-blocking debt item is recorded
  (`UEF5_3_DEBT_001`: live-ledger hashing during pytest is a test/observability efficiency debt, not a
  correctness or freeze blocker).
- Detail: [docs/research/uef5_3_historical_dual_run.md](../research/uef5_3_historical_dual_run.md).

## Verification (at freeze)

- Freeze manifest (UEF-1..3C): `11 / 11 MATCH`.
- UEF-5.1 and UEF-5.2: unchanged (`git diff` clean against their frozen file sets).
- No UEF-5.3 implementation code was changed during this documentation/freeze task.
- Focused UEF-5.3 tests: 31 passed (`tests/test_uef5_3_dual_run.py`).
- Combined implementation-side run: 31 UEF-5.3 + 117 UEF-5.2 = 148 passed, 0 assertion failures (this is
  Claude's own recorded evidence, distinct from Codex's `TEST_EVIDENCE: PARTIAL` note -- see the freeze
  record's "Test evidence note" for why that distinction matters and is preserved, not smoothed over).
- Final audited real run `UEF53DUAL_5e22b07eb2a62894`: 4359 total comparison units, 0 unexplained
  divergences, 0 unaccounted, 0 collisions.

## Governance

`docs/daily_patch/README.md`'s existing "When To Add An Entry" rule applies unchanged (formal freezes,
architecture decisions, production/runtime safety fixes, research-lifecycle changes, major incidents,
major roadmap changes -- not routine tests/refactors/formatting).
