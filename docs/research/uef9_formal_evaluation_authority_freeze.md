# UEF-9 — Formal Evaluation Authority — Formal Freeze

Status: **FORMALLY FROZEN** (independent final closure audit: `CORE_VERDICT: APPROVE_UEF9`,
`UEF9_COMPLETE: YES`, `UEF9_FORMAL_FREEZE: YES`, `UEF_COMPLETE: YES`, CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0).
Not to be modified again unless a reproducible correctness bug, a proven authority contradiction, or a
safety violation is discovered -- never for refactor, naming, performance polish, new ranking, strategy
tuning, or convenience fields.

UEF-9 is the FINAL UEF stage. It does not evaluate strategies again, does not rank candidates, does not
recompute metrics, and does not reopen raw evidence. Its sole purpose is to **bind the already-frozen
UEF-7 and UEF-8 evaluation authorities into one final, verifiable, fail-closed authority contract**.
Checkpoint commit: `608ddff`.

**With UEF-9's formal freeze, the Unified Evaluation Foundation (UEF-1 through UEF-9) is now semantically
COMPLETE.**

## Closure lineage (summary)

1. First delivery (drafted by an independent Codex implementation pass, then reviewed and verified line by
   line by Claude before this closure): `model.py` (`FormalEvaluationAuthority` manifest, `VALID`/`INVALID`
   status), `authority.py` (`verify_formal_evaluation_authority` -- fail-closed binding verifier), `run_identity.py`
   (deterministic `UEF9RUN_<digest>` identity), `reporter.py` (presentation-only manifest writer).
2. Independent review (Claude) confirmed the implementation correct end to end (real 14-candidate,
   91-pair board verified `VALID`; every required fail-closed condition genuinely reachable; no
   candidate/pair count ever hardcoded in the verifier) and made two bounded, non-semantic improvements:
   (a) documented why `_CURRENT_SCHEMA_COMPARABLE_REACHABLE` is a schema-version-locked capability
   declaration rather than a hardcoded real-data value; (b) added a regression that isolates the
   "current UEF-7 schema declares COMPARABLE unreachable" fail-closed guard from the more general
   per-status summary-count-mismatch guard, which the original test suite exercised only incidentally.
3. Final independent closure: `CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0`, `CORE_VERDICT: APPROVE_UEF9`,
   `UEF9_COMPLETE: YES`, `UEF9_FORMAL_FREEZE: YES`, `UEF_COMPLETE: YES`.

## Final regression state

```
UEF-9:  20 PASS
UEF-8:  41 PASS
UEF-7:  38 PASS
TOTAL:  99 PASS
```

## Frozen-predecessor safety

- UEF-1..UEF-3C freeze manifest: `11 / 11 MATCH`.
- UEF-5.1, UEF-5.2, UEF-5.3, UEF-6, UEF-7, UEF-8, and Alpha Board v2: unchanged -- UEF-9 never recalculates
  UEF-7's normalized facts or UEF-8's comparison-validity facts, and never reopens raw Alpha Board sources,
  Q artifacts, UEF-6 witness files, UEF-5 historical artifacts, or runtime/broker state.

## Authoritative contract

### Final authority ownership

```
candidate evaluation authority     -> UEF-7
pairwise comparison-validity authority -> UEF-8
final evaluation authority binding -> UEF-9

ranking authority   -> NONE
promotion authority  -> NONE
trading authority    -> NONE
```

UEF determines evidence/evaluation VALIDITY. It never makes a trading decision.

### UEF-7 authority (unchanged, consumed only)

UEF-7 owns normalized candidate-level evaluation facts: candidate identity, question, target horizon,
evidence cohort, normalized metrics, sample/accounting values, source provenance, population proof status,
operation truth. UEF-9 reads these fields exactly as UEF-7 publishes them (`uef7.alpha_board_normalization.v1`)
and never duplicates or recomputes them.

### UEF-8 authority (unchanged, consumed only)

UEF-8 owns pairwise comparison validity: `COMPARABLE` / `CONDITIONAL` / `NOT_COMPARABLE`, with their full
`comparison_reasons`. UEF-9 accepts these as upstream authority (`uef8.fair_comparison.v1`) and never
re-runs the question/horizon/cohort/metric-availability/population-relation/source-provenance rules or
reason precedence that UEF-8 already owns.

### Current population limitation (frozen, not a bug)

```
COMPARABLE_REACHABLE_WITH_CURRENT_UEF7_SCHEMA: NO
```

The frozen `uef7.alpha_board_normalization.v1` schema exposes no pairwise population-relation authority.
Individual population proof (a row's own `population_identity_status`) is not the same as PAIRWISE
population relation proof; the current schema provides only the former. `POPULATION_RELATION_NOT_PROVEN`
is therefore retained across every current-schema pair -- an explicit, frozen authority limitation, not a
defect.

### UEF-8 missing native semantic digest (frozen handling)

Codex independently confirmed `UEF8_NATIVE_SEMANTIC_DIGEST: ABSENT` -- UEF-8's own frozen output carries no
single field representing a content digest of its own comparison results (only `uef7_normalized_semantic_digest`,
the UPSTREAM UEF-7 digest, and its own `uef8_run_id`/`uef8_implementation_digest`). UEF-9 therefore computes
its own canonical digest over the supplied UEF-8 authority object
(`run_identity.canonical_uef8_authority_digest`) for LOCAL binding/integrity purposes only. This digest is
explicitly **not** a native UEF-8 semantic digest and must never be relabeled as one.

### Conservation invariants

```
UEF-7 candidate universe conserved
UEF-8 candidate universe == UEF-7 candidate universe (set equality, no duplicates)

for N candidates: pair_count = N*(N-1)/2
pair_count = unique semantic (left, right) pairs = unique comparison_pair_ids

pair_count = COMPARABLE + CONDITIONAL + NOT_COMPARABLE
```

Any contradiction fails closed (`UEF9AuthorityError`) -- never a silent repair, never a partial-valid or
confidence-scored result.

### Authority status model

Exactly two states: `VALID` (every frozen binding/invariant passes) or a raised `UEF9AuthorityError`
(fail-closed). No `partial-valid`, `warning-valid`, `authority_score`, or `confidence_score` of any kind.

### Fail-closed matrix

```
wrong UEF-7 schema                          wrong UEF-8 schema
UEF-8 source-binding mismatch (run id / normalized-semantic-digest / through_day)
candidate-count mismatch                     candidate-set mismatch
duplicate candidate ID
pair-count mismatch                          missing pair
self-pair                                    duplicate semantic pair
duplicate comparison_pair_id                 unknown pair candidate
unknown comparison status                    status-count mismatch (per-status and pair_count)
current-schema capability contradiction (COMPARABLE > 0 while unreachable)
```

Every one of these is independently reachable and covered by a dedicated regression (see
`tests/test_uef9_formal_authority.py`).

### Run identity

`UEF9RUN_<digest>` binds: the source UEF-7 run id, UEF-9's own independently-verified UEF-7
normalized-rows digest, the source UEF-8 run id, UEF-9's own derived UEF-8 authority digest, a candidate-ids
digest, a comparison-pair-ids digest, the UEF-9 implementation digest, the UEF-9 schema version, and the
authority contract version. No timestamp, mtime, wall clock, filesystem iteration order, or `generated_at`
contamination of any kind. Candidate and pair input ordering is non-semantic (verified: reversing either
list produces the identical digests and run id).

### Pair identity (inherited UEF-8 invariant)

```
canonical ordered candidate pair -> canonical structured JSON -> SHA-256 -> UEF8PAIR_<digest>
```

A pair-ID collision fails closed. No delimiter-based pair identity is ever authoritative.

### Document/runtime boundary

Docs are human/specification authority, never runtime authority. UEF-9 code never parses
`docs/research/`, `docs/milestones/`, `docs/daily_patch/`, or any README to establish evaluation validity
-- only frozen code-level schemas/contracts and the supplied UEF-7/UEF-8 input objects.

### Authoritative vs derived vs non-authority surfaces

```
AUTHORITATIVE: UEF-7 normalized candidate facts, UEF-8 pairwise comparison facts, UEF-9 final binding
DERIVED (diagnostic only): counts, reason summaries, coverage summaries, Markdown rendering
NON-AUTHORITY: temporary reports, manual analyst opinion, LLM interpretation, unfrozen experiments,
               raw-path heuristics, live runtime/broker artifacts
```

## Real final authority snapshot (measured, not hardcoded)

```
candidate_count: 14
pair_count: 91
COMPARABLE: 0
CONDITIONAL: 7
NOT_COMPARABLE: 84
authority_status: VALID
```

These are current observed evidence values, never constants inside `authority.py` -- the verifier derives
`N*(N-1)/2`, candidate sets, and status counts dynamically from whatever UEF-7/UEF-8 objects it is given.

## UEF-9 -> Strategy Program Integration boundary

The next program is **Strategy Program Integration**, not "UEF-10." UEF-1 through UEF-9 remain the frozen
evaluation-authority foundation underneath it; Strategy Program Integration consolidates operational
research/strategy lifecycle semantics on top of that frozen foundation, never inside it.

## Related

- [UEF milestones](../milestones/UEF.md)
- [UEF-7 Alpha Board Normalization Freeze](uef7_alpha_board_normalization_freeze.md)
- [UEF-8 Fair Comparison Validation Freeze](uef8_fair_comparison_validation_freeze.md)
- [UEF freeze manifest](uef_freeze_manifest.md)
