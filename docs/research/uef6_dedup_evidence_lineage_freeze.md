# UEF-6 — Dedup & Evidence Lineage — Formal Freeze

Status: **FORMALLY FROZEN** (independent Codex final closure audit: `CORE_VERDICT: APPROVE_UEF6`,
`UEF6_COMPLETE: YES`, `UEF6_FORMAL_FREEZE: YES`, CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0). Not to be modified
again unless a reproducible correctness defect, an execution-safety violation, or a proven downstream
contract contradiction is discovered.

UEF-6 answers, over the frozen UEF-1..UEF-5.3 evaluation foundation: which observed rows are the same
evidence counted twice, and which persisted aggregates can be PROVEN (not inferred) to have been built
from which exact evaluation records. It never re-derives, re-computes, or backfills any frozen record.

| Sub-phase | Scope | Status |
|---|---|---|
| UEF-6A | Population Dedup Detection | APPROVED / COMPLETE |
| UEF-6B | Direct Evidence Lineage Sidecar | APPROVED / COMPLETE |
| UEF-6C | Historical Dedup & Direct-Lineage Validation | APPROVED / COMPLETE |
| UEF-6 | (combined) | **FORMALLY FROZEN** |

Checkpoint commits: UEF-6A `ab699bb`, UEF-6B `b1dbe5e`, UEF-6C `657ddaa`.

## Final audit

`CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0`. UEF-6C's own final audit (prior to this freeze) found 4 concrete
defects (A: validation run identity was row-order sensitive across evaluator-version ties; B:
`lineage_coverage.py` was omitted from the UEF-6C semantic implementation digest; C: witness↔aggregate
accounting could match on `evaluation_record_id` alone, letting one witness falsely cover two context-
different aggregates; D: duplicate-member historical totals conflated "distinct duplicated identity kinds"
with "excess occurrence count") — all four corrected and independently re-verified before this freeze.

## Final regression state

```
UEF-6A: 22 PASS
UEF-6B: 14 PASS
UEF-6C: 28 PASS
TOTAL:  64 PASS
```

## Frozen-predecessor safety

- UEF-1..UEF-3C freeze manifest: `11 / 11 MATCH`.
- UEF-5.1, UEF-5.2, UEF-5.3: unchanged (`git diff` clean against their frozen file sets).
- No UEF-6A or UEF-6B semantic file was modified while closing UEF-6C or during this freeze.

## UEF-6A — Population Dedup Detection

Pure classifier (`libs/reporting/evaluation/uef6/population_dedup.py::analyze_episode_population`) over an
already-loaded, already-identity-validated `EpisodeRecord` population. Distinguishes four population
countings that are easy to conflate:

- **raw row count** — every loaded episode row, duplicates included.
- **canonical physical event count** — unique `canonical_event_id`.
- **evaluation subject count** — unique `evaluation_subject_id`.
- **evaluation record count** — unique `evaluation_record_id`.

Reuses the frozen UEF-1 `classify_duplicate_relation()` verbatim (never re-derived) and preserves every
frozen relation distinctly, including `ACCIDENTAL_DUPLICATE`, `LEGITIMATE_MULTI_HYPOTHESIS`,
`SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION`, and `SAME_SUBJECT_DIFFERENT_EXECUTION_MODE`. No new canonical
identity authority is introduced anywhere in UEF-6; `cross_program_link_key` remains explicitly
non-authoritative (never an input to any duplicate/identity decision). An identity/content collision
(same `evaluation_record_id` + `evaluator_version`, different body) fails closed
(`UEF6IdentityContentCollisionError`) rather than silently choosing or merging a row.

Run identity (`UEF6A_RUN_ID`) is bound to an order-independent MULTISET digest
(`population_semantic_digest`) over the full canonical episode population, never a raw file-byte hash —
permuting input row order never changes the run id; a semantic or multiplicity change always does.

### Real historical result

Authoritative measured baseline, target `UEF5RUN_bc1e299667c2ca94b977`:

```
raw episode rows:            107
unique canonical events:      80
unique evaluation subjects:  107
unique evaluation records:   107
accidental duplicate groups:   0
duplicate excess:              0
multi-evaluation physical events: 6
LEGITIMATE_MULTI_HYPOTHESIS:  75 pairwise relations
```

`75` is a **pairwise relation count** (how many same-event, different-hypothesis pairs were classified
`LEGITIMATE_MULTI_HYPOTHESIS`), not 75 duplicate rows — no row is discarded, merged, or double-counted as
an accidental duplicate on that basis.

## UEF-6B — Direct Evidence Lineage Sidecar

`libs/reporting/evaluation/uef6/lineage_witness.py::aggregate_canonical_samples_with_lineage` calls the
frozen `aggregate_canonical_samples()` EXACTLY ONCE and returns both the unmodified `AggregateRecord` and a
`AggregateLineageWitness` built from the SAME batches — zero PF/MDD/net-return math reimplemented.

**Exact aggregate lineage requires a DIRECT aggregation-member witness.** No authoritative lineage may be
reconstructed after the fact from `AggregateRecord` + `EpisodeRecord` population + matching
day/symbol/hypothesis/horizon/count alone — count equality is never accepted as population identity proof.
Without a direct witness, the only honest answer is `DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE`
(`lineage_status_without_direct_witness()`, a zero-argument function that structurally cannot infer
membership from anything). UEF-6B remains a sidecar: `AggregateRecord`, `EpisodeRecord`,
`CanonicalAggregationMember`, and `aggregate_canonical_samples()` were not modified.

## UEF-6C — Historical Dedup & Direct-Lineage Validation

Validation-only instrumentation harness (`libs/reporting/evaluation/uef6/validation_replay.py`) separates
two historical evidence modes:

- **Mode A** — frozen-output observation: runs UEF-6A directly over an already-persisted
  `episodes.jsonl`. Authoritative for episode dedup; never substitutes for Mode B.
- **Mode B** — instrumented historical replay: re-runs the frozen UEF-5.2 pipeline
  (`historical_recompute.run_historical_recompute`) over an isolated, byte-verified snapshot with
  aggregation calls intercepted (`unittest.mock.patch.object`, scoped to one `with` block, restored on any
  exit including an exception) through the UEF-6B wrapper, capturing a real direct witness per aggregation
  call. Required for any DIRECT lineage claim; Mode A evidence is never used to infer Mode B conclusions.

Mode A never substitutes for Mode B, and Mode B's canonical output must be proven byte-identical to an
uninstrumented baseline replay over the same snapshot before any witness may be linked to that replay
(`link_witnesses_to_frozen_result`) — instrumentation is proven to leave the frozen pipeline's own output
semantically untouched, never merely assumed.

### Real instrumentation validation

Stable real fixture (`reports/evaluation/opportunity_engine_shadow/2026-09-22`, Q11 v2, isolated snapshot):

```
baseline vs instrumented canonical parity: PASS
aggregate calls:      6
captured witnesses:   6
original frozen aggregator restored: PASS
```

### Real historical replay limitation (target run)

```
target:  UEF5RUN_bc1e299667c2ca94b977
Mode B:  NOT_REPRODUCIBLE
```

Reason: the historically recorded source sha256 (`51615b9c...`) for one of the target run's discovered
input artifacts no longer matches its current sha256 (`669d81bc...`) — the live trading host continued
writing to that same-day file after the target run was captured. No authoritative exact-byte archive of
the original bytes was found anywhere in the current repository (git does not track this path; no
content-addressed receipt/raw-archive copy exists for it). Consequently:

- no historical lineage witness was fabricated for this target run,
- no approximate replay was accepted as if it were exact,
- no retroactive FULL lineage claim was assigned to the frozen historical artifact.

This is **NON-BLOCKING for the UEF-6 freeze** — fail-closed behavior under an unrecoverable byte mismatch
is the correct contract, not a defect. It is also **not** a transient condition: once current bytes diverge
from the historically recorded bytes, simply waiting does not reconstruct the original bytes; this classifies
as `NOT_REPRODUCIBLE_FROM_CURRENT_REPOSITORY_STATE`, recoverable only if an authoritative exact-byte copy is
later found.

### Duplicate-member semantics (frozen distinction)

`duplicate_member_identity_count` = the number of DISTINCT evaluation-record identities that occur more
than once within one aggregate. `duplicate_member_excess_count` = the sum of occurrences beyond the first,
across those repeating identities. These are different numbers and must never be conflated:

```
members: REC_A, REC_A, REC_A, REC_B
duplicate_member_identity_count = 1   (one distinct id repeats: REC_A)
duplicate_member_excess_count   = 2   (REC_A occurs 3x -> 2 excess occurrences)
```

### Witness ↔ aggregate match authority (final audit fix)

Final matching authority is the FULL semantic key:

```
evaluation_record_id + canonical_aggregate_id + full MetricAggregationContext digest
```

— never `evaluation_record_id` alone, which two context-different aggregates (e.g. different horizon or
policy) can legitimately share. Accounting is occurrence-level multiset (`collections.Counter` over the
full key), never a set/dict keyed only by record id: one witness occurrence may cover at most one
persisted-aggregate occurrence of the identical full key, and vice versa. A persisted `AggregateRecord`
whose own `identity` disagrees with the identity embedded in its `metrics['context']['aggregate_identity']`
fails closed (`UEF6AggregateIdentityConsistencyError`) rather than building a match key from a contradictory
identity.

### UEF-6C deterministic validation identity

Validation identity uses order-independent, multiplicity-sensitive semantic digests
(`episode_population_semantic_digest`, `aggregate_population_semantic_digest`) over the full canonical
content of each row — never a stable sort keyed on `evaluation_record_id` alone, which leaves rows sharing
that key (evaluator-version variants; context-different aggregates) in their original input order and makes
the digest, and therefore `UEF6C_RUN_ID`, row-order sensitive.

```
[A, B]  permuted to  [B, A]   -> same validation identity
[A, B]  vs           [A, B, B] -> different validation identity (never set semantics)
```

`UEF6C_RUN_ID` binds: target UEF-5.2 run id, the episode semantic digest, the aggregate semantic digest,
UEF-6A/6B/6C semantic implementation digests, the effective replay/validation config identity, and the
validation schema version. The UEF-6C semantic implementation digest covers every UEF-6C module capable of
changing validation semantics — `validation_replay.py` and `lineage_coverage.py` (witness↔aggregate
accounting, population coverage, duplicate-member totals, cross-aggregate reuse) — never tests, never
CLI-only presentation code that does not affect the semantic result.

## Authority summary

No new canonical identity system exists anywhere in UEF-6. UEF-6A/6B/6C are read-only, additive evidence
layers over the frozen UEF-1..UEF-5.3 foundation: they classify, witness, and validate — they never
mutate, backfill, or invent a frozen record.

## Related

- [UEF milestones](../milestones/UEF.md)
- [UEF-5.1 Clean Evidence Registry](uef5_1_clean_evidence_registry.md)
- [UEF-5.2 Historical Recompute](uef5_2_historical_recompute.md)
- [UEF-5.3 Historical Dual Run](uef5_3_historical_dual_run.md)
- [UEF freeze manifest](uef_freeze_manifest.md)
