# UEF-7 — Alpha Board Normalization — Formal Freeze

Status: **FORMALLY FROZEN** (independent Codex final closure audit: `CORE_VERDICT: APPROVE_UEF7`,
`UEF7_COMPLETE: YES`, `UEF7_FORMAL_FREEZE: YES`, CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0). Not to be modified
again unless a reproducible correctness defect, a proven downstream contract contradiction, or an
execution/safety violation is discovered -- never for refactor, naming, performance polish, or
convenience fields.

UEF-7 produces one deterministic, comparison-ready NORMALIZED VIEW over the frozen Alpha Research Board
v2 (`libs/reporting/alpha_research_board`), without changing any candidate, strategy, metric, decision,
promotion state, or runtime behavior. It is a read-only derived sidecar: the original board is never
replaced, never written to, and never called differently. Checkpoint commit: `cc7fb4b`.

## Closure lineage (summary)

1. First delivery: `model.py` / `alpha_board_normalization.py` / `run_identity.py` / `reporter.py`,
   deriving normalized rows, source-provenance overlap groups, and an explicit population-proof status
   over the real 14-candidate board.
2. Codex bounded correction (2 HIGH): (A) source-provenance grouping and `source_bundle_id` used a
   partial `(source_key, path)` key, so two references agreeing on those but disagreeing on
   `available`/`error` were wrongly treated as identical. (B) the Board semantic digest hashed the raw
   input mapping, so a contract-external top-level field (e.g. a caller-added `generated_at`) changed the
   UEF-7 run id even though normalization itself ignored it. Fixed: (A) a single canonical
   `SourceReference` serializer (`model.py::canonical_source_reference`) binding all four fields
   (`source_key`, `path`, `available`, `error`) became the one shared identity authority for grouping,
   bundle id, and duplicate-reference detection; (B) `run_identity.py::alpha_board_semantic_digest` now
   hashes an explicit Board v2 contract-surface projection (the 17 top-level fields
   `canonicalize_board()` actually publishes), never the raw mapping, so a genuinely contract-external
   field can never influence semantic identity.
3. Codex bounded re-audit (1 HIGH): candidate rows were validated against the board's OWN
   `board["row_columns"]` field, which an adversarial input could extend in lockstep with every candidate
   row to smuggle a contract-external field past validation while it still influenced the semantic digest.
   Fixed: row-contract validation now trusts ONLY the imported, frozen
   `libs.reporting.alpha_research_board.contracts.ROW_COLUMNS` -- `board["row_columns"]` itself must equal
   it exactly (ordered) before any per-row check runs, and each candidate row's key SET is checked
   against that same frozen authority, never the board-published field. The input can no longer expand
   its own semantic schema.
4. Final Codex closure: `CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0`, `CORE_VERDICT: APPROVE_UEF7`,
   `UEF7_COMPLETE: YES`, `UEF7_FORMAL_FREEZE: YES`.

## Final regression state

```
UEF-7:        38 PASS
Alpha Board:  36 PASS
UEF-6A:       22 PASS
UEF-6B:       14 PASS
UEF-6C:       28 PASS
TOTAL:       138 PASS
```

## Frozen-predecessor safety

- UEF-1..UEF-3C freeze manifest: `11 / 11 MATCH`.
- UEF-5.1, UEF-5.2, UEF-5.3, UEF-6 (all of UEF-6A/6B/6C): unchanged.
- Alpha Board v2 (`libs/reporting/alpha_research_board/*`): unchanged -- UEF-7 never calls
  `canonicalize_board()`/`build_alpha_research_board()` differently, never adds a field to the frozen
  `ROW_COLUMNS`, never mutates a candidate row.

## Authoritative contract

### Candidate rows are not evidence populations

```
candidate row != independent evidence population
```

The current real board has 14 candidate rows. This does **not** imply 14 independent evidence
populations -- UEF-7 never claims or infers that.

### Source provenance is not population identity

```
same source provenance  != same population
different source provenance != proven independence
```

For the current Alpha Board v2, `population_identity_status` is always `NOT_PROVABLE_FROM_ALPHA_BOARD_V2`
(real result: `proven_population_group_count=0`, `unresolved_population_candidate_count=14`). No
evidence-independence count is ever invented; unresolved rows are reported honestly as unresolved, never
as a computed independence figure.

### Source reference identity (full four-field key)

The canonical `SourceReference` binds all four normalized fields together as ONE identity:

```
source_key + path + available + error
```

Shared-source grouping and `source_bundle_id` both use this SAME authority -- never a partial
`(source_key, path)` key. Two references agreeing on `source_key`/`path` but disagreeing on
`available`/`error` are different references and are never grouped or bundled together.

### Source bundle multiset semantics

```
[A, B]     permuted to [B, A]  -> SAME source_bundle_id
[A, B]     vs          [A,B,B] -> DIFFERENT source_bundle_id
```

Duplicate source occurrences are preserved and reported (`DUPLICATE_SOURCE_REFERENCE:*` in
`source_anomalies`), never silently set-collapsed.

### Alpha Board trust root

UEF-7 trusts the frozen `libs.reporting.alpha_research_board.contracts.ROW_COLUMNS` as the SOLE candidate-
row contract authority. Trust chain:

```
frozen ROW_COLUMNS
  -> board["row_columns"] must equal it exactly, in order
  -> every candidate row's key set must equal it exactly
  -> normalization
  -> Board semantic digest
  -> UEF7 run identity
```

The input can never expand its own semantic schema -- neither by extending `board["row_columns"]` nor a
candidate row, together or separately.

### Top-level semantic surface

The Board semantic digest is computed from an explicit Alpha Board v2 contract-surface projection (the
same 17 top-level fields `canonicalize_board()` publishes: `schema_version`, `contract_version`,
`behavior_effect`, `through_day`, `authority`, `cost_authority`, `questions`, `candidate_count`,
`candidate_ids`, `row_columns`, `feature_columns`, `candidates`, `closeout_summary`, `settled_findings`,
`integrity`, `sources`, `behavior_change_authorized`), never the raw input mapping. A top-level
contract-external field (`generated_at`, an arbitrary debug field, etc.) never affects normalized
semantics, the Board semantic digest, or the UEF7 run id, provided it stays outside that consumed
surface. Candidate row extensions remain invalid regardless, because rows carry their own frozen,
separately-enforced contract (`ROW_COLUMNS`).

### Metric / operation truth preservation

UEF-7 is structural normalization only -- no recomputation of win rate, average return, profit factor,
max drawdown, MFE, MAE, or cost. Every `net_metrics` value is copied verbatim (`None` stays `None`,
missing stays missing, `0` is never invented). `status`, `operation_status`, `fixed_validation_status`,
`production_promotion_status`, and `decision` are copied exactly, with an explicit re-verification
(`UEF7OperationTruthMismatchError`) that fails closed on any disagreement.

### No-ranking boundary

UEF-7 introduces no `score`, `rank`, `tier`, `winner`, `best_candidate`, promotion recommendation, or
strategy recommendation. The existing Board candidate order is preserved verbatim. Fair-comparison policy
belongs to UEF-8, not UEF-7.

## Real board result (measured, not hardcoded)

```
through_day: 2026-09-25
candidate rows: 14
shared source groups: 5
rows with shared source: 10
proven population groups: 0
unresolved population candidates: 14
```

Shared source groups: `btc_woori_history`, `feature_candidates`, `opening_cumulative`,
`prospective_candidates`, `short_alpha_discriminator` -- provenance overlap groups only, never a
population or duplicate-row claim.

The `opening_cumulative` group's membership is dynamically derived, not hardcoded UEF-7 logic, and
currently contains `IMMEDIATE_OPENING_PROBE`, `CONFIRMED_RECURRENT_RANK`, `DISLOCATION_REBOUND`,
`OPEN_0_20_RANK1_30M`. `R1_SCANNER_RISK_HIGH_30M_V1` currently comes from `feature_candidates` /
`prospective_candidates` and is **not** a member of `opening_cumulative` -- correcting an obsolete
historical assumption about that candidate's provenance.

## Output authority

UEF-7 output is a derived evaluation normalization view. It is **not** runtime authority, trading
authority, promotion authority, or fair-comparison authority. UEF-8 owns comparison admissibility.

## Related

- [UEF milestones](../milestones/UEF.md)
- [UEF-6 Dedup & Evidence Lineage Freeze](uef6_dedup_evidence_lineage_freeze.md)
- [UEF freeze manifest](uef_freeze_manifest.md)
