# 2026-09-29 UEF-7 Formal Freeze

## Scope

Formally freezes UEF-7 (Alpha Board Normalization). Evaluation/reporting integrity only -- no Scanner
ranking, Strategist behavior, Commander approval, Monitor entry/exit rules, position sizing, or broker
execution is affected. UEF-7 is entirely read-only against the frozen Alpha Research Board v2 and
UEF-1..UEF-6.

## UEF-7 — Alpha Board Normalization

- IMPLEMENTED: a deterministic, comparison-ready normalized view over the live Alpha Research Board v2 --
  14 candidate rows preserved (no merge, no collapse, no reordering), full four-field `SourceReference`
  provenance (`source_key` + `path` + `available` + `error`), deterministic source-provenance overlap
  grouping and multiset-sensitive `source_bundle_id`, explicit `population_identity_status` kept
  `NOT_PROVABLE_FROM_ALPHA_BOARD_V2` (no evidence-independence count ever invented), a frozen
  `ROW_COLUMNS` trust root, and a deterministic Board-semantic-digest-bound `UEF7_RUN_ID`. No ranking,
  scoring, promotion, or strategy change of any kind.
- Codex bounded correction (2 HIGH): source-provenance grouping/bundle identity used a partial key
  (ignoring `available`/`error`); the Board semantic digest hashed the raw input mapping instead of an
  explicit contract-surface projection, letting a contract-external top-level field change the run id.
  Both fixed.
- Codex bounded re-audit (1 HIGH, trust-root defect): candidate-row validation trusted the board's OWN
  published `row_columns` field, which an adversarial input could extend in lockstep with every row to
  smuggle a contract-external field past validation. Fixed: row-contract validation now trusts only the
  imported, frozen `ROW_COLUMNS` from Alpha Board v2's own contract module.
- APPROVED and FORMALLY FROZEN by an independent Codex final closure audit: `CRITICAL 0, HIGH 0, MEDIUM 0,
  LOW 0`, `CORE_VERDICT: APPROVE_UEF7`, `UEF7_COMPLETE: YES`, `UEF7_FORMAL_FREEZE: YES`. Checkpoint commit
  `cc7fb4b`.
- Detail: [docs/research/uef7_alpha_board_normalization_freeze.md](../research/uef7_alpha_board_normalization_freeze.md).

## Verification (at freeze)

- Freeze manifest (UEF-1..3C): `11 / 11 MATCH`.
- UEF-5.1, UEF-5.2, UEF-5.3, UEF-6, and Alpha Board v2: unchanged (`git diff` clean against their frozen
  file sets).
- No UEF-7 semantic file was changed during this documentation/freeze task.
- Focused regression: UEF-7 38 passed, Alpha Board 36 passed, UEF-6A 22 passed, UEF-6B 14 passed, UEF-6C
  28 passed -- 138 passed, 0 failures.
- Real board (`through_day=2026-09-25`): 14 candidate rows, 5 shared-source groups, 10 rows with shared
  source, 0 proven population groups, 14 unresolved population candidates -- all derived dynamically, none
  hardcoded.

## Governance

`docs/daily_patch/README.md`'s existing "When To Add An Entry" rule applies unchanged (formal freezes,
architecture decisions, production/runtime safety fixes, research-lifecycle changes, major incidents,
major roadmap changes -- not routine tests/refactors/formatting).

## Next

UEF-8 Fair Comparison Validation is NEXT. Not started by this closure.
