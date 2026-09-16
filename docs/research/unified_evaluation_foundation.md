# Unified Evaluation Foundation (UEF-1) — Work Package A

Status: **UEF-1 FORMALLY FROZEN (2026-09-13, Codex Final Freeze Audit: APPROVE_UEF1,
CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0)**. The Closure Reset narrative below is kept as
historical record of how the frozen contract was reached; every section it describes is
now the frozen Record/Identity/Relation/Lineage contract, not a pending draft. UEF-2A
(forward semantics inventory + policy contract, no engine) has started under this frozen
contract — see `docs/research/uef2_forward_semantics_inventory.md`.

## UEF phase boundary (Closure Reset — response to the third and fourth Codex REJECT_WORK_PACKAGE_A verdicts)

After three patch rounds (Fix1→Fix2→Fix3) that each closed real defects
but kept expanding what "Work Package A" was expected to prove, the
Closure Reset re-fixes the boundary explicitly, so this document is never
used again to justify Work Package A absorbing a later phase's job:

| Phase | Owns |
|---|---|
| **UEF-1 (this package)** | Canonical terminology (contracts.py), the four-record family and its identity model (record.py, identity.py), structural relation validation, and **representability** — proof that every legacy family's load-bearing semantics CAN be expressed in the canonical shape, via realistic construction from real artifacts. |
| **UEF-2** | Canonical forward-return engine (the checkpoint/horizon calculation authority the 2026-09-12 integrity review found duplicated ~10 times across Q9-Q18/Opening Alpha). |
| **UEF-3** | Canonical cost & metric engine (WR/PF/Avg/MFE/MAE aggregation authority, replacing the ~6 independently-written versions the same review found). |
| **UEF-4** | Full legacy adapter layer — code that reads a real Q9-Q18/Opening Alpha/Alpha Board artifact and PRODUCES a canonical record automatically, with a full round-trip-verified adapter test per family. |

**UEF-1's own acceptance is REPRESENTABILITY, not full adapter
implementation.** A family PASSES representability when: every
load-bearing field has a canonical destination (a typed field, not a
fabricated value); no two genuinely different real facts collide into
one canonical value (no semantic collision); and nothing is silently
dropped. Building a `q11_legacy_adapter.py` that performs this mapping
automatically from a raw file, with no human-written glue, is explicitly
**UEF-4's job, not UEF-1's** — this document previously asked Work
Package A's acceptance criteria to include "full 12-family semantic
roundtrip," which repeatedly pulled UEF-4 scope into UEF-1 audits and is
the reason this reset exists. The tests in this package's own test file
still perform a real construction + serialize/deserialize round-trip per
family (stronger evidence than the representability bar strictly
requires) — they are simply no longer *labeled or required* as "full
adapter" proof, and no adapter module is added anywhere in `libs/` outside
this package.

---

## Full UEF roadmap (UEF-1..UEF-9) — 2026-09-13 consolidation

This extends the 4-row phase-boundary table above to the full plan. Rows
1-4 are unchanged from that table (repeated here for a single point of
reference); rows 5-9 are new. **No engine/adapter code exists past UEF-2A.**
UEF-1 is now FROZEN (see the Status line at the top of this document); UEF-2
has begun, sub-phased as UEF-2A (semantics inventory + policy contract,
2026-09-13, COMPLETE) → UEF-2B (engine, NOT STARTED) → UEF-2C (golden
parity/edge-case/artifact validation, NOT STARTED) → Codex Final Freeze.

| Phase | Owns | Depends on | Status |
|---|---|---|---|
| **UEF-1** | Canonical evaluation contract/record/identity model, structural relation validation, representability proof (this Work Package) | — | **FORMALLY FROZEN** (Codex Final Freeze Audit, 2026-09-13) |
| **UEF-2** | Canonical forward-return / checkpoint calculation engine — the single authority replacing the ~10+ duplicated forward-checkpoint engines `docs/research/uef2_forward_semantics_inventory.md` found across Q9-Q18/Opening Alpha | UEF-1 (frozen `Checkpoint`/`EventRef` shapes) | UEF-2A (inventory + `ForwardPolicy` contract) COMPLETE; UEF-2B (engine) NOT STARTED |
| **UEF-3** | Canonical cost & metric engine (WR/PF/Avg/MFE/MAE aggregation), replacing the ~6 independently-written aggregate-statistics engines and the confirmed PF zero-loss float-vs-string divergence | UEF-1, UEF-2 (metrics consume checkpoint output) | PLANNED |
| **UEF-4** | Legacy adapter layer — automated code that reads a real Q9-Q18/Opening Alpha/Alpha Board artifact and produces a canonical record with no human-written glue, one round-trip-verified adapter per family | UEF-1 (adapter output must satisfy UEF-1's record contract) | UEF-4A (inventory, `docs/research/uef4_legacy_family_inventory.md`) FORMALLY FROZEN; UEF-4B-1 (Q10 Semiconductor adapter, `libs/reporting/evaluation/canonical/adapters/q10_semiconductor.py`) implementation complete, awaiting independent audit; UEF-4B-2+ NOT STARTED |
| **UEF-5** | Historical recompute & dual-run — run UEF-2/UEF-3 in shadow parallel against every legacy program's real history, without substituting any production number | UEF-2, UEF-3, UEF-4 (needs adapters to get legacy data into canonical shape first) | PLANNED |
| **UEF-6** | Dedup & evidence lineage — mechanical detection of the same underlying episode counted more than once across programs/rows (the concrete fix for the Alpha Board's confirmed double-counting), using `canonical_event_id`/`evaluation_subject_id` and `classify_duplicate_relation()` at population scale | UEF-1 (identity model), UEF-5 (needs real recomputed population to run detection against) | PLANNED |
| **UEF-7** | Alpha Research Board normalization — migrate the Board's own display/ranking logic to read canonical records instead of its own ad hoc calculators, resolving the three-way `status` conflation this design already separates (§3.5) | UEF-3 (canonical metrics), UEF-6 (dedup must exist before the Board can trust cross-row comparisons) | PLANNED |
| **UEF-8** | Fair-comparison validation — a gate that certifies two hypotheses are being compared on genuinely equivalent terms (same cost model, same horizon semantics, same sample-quality bar) before any cross-program ranking is presented as fact | UEF-3, UEF-6, UEF-7 | PLANNED |
| **UEF-9** | Formal freeze / evaluation authority declaration — the point at which canonical UEF output, not any legacy calculator, becomes the system's evaluation authority for a given metric, per metric, not all-at-once | UEF-1..UEF-8 all closed | PLANNED |

### UEF / Q100 dependency (authority boundary)

**UEF is the Measurement Authority. Q100 is the Research/Learning
Authority.** These are deliberately separate and must never merge:

- UEF owns *how a number is calculated* — checkpoints, costs, metrics,
  identity, dedup, fair comparison. Nothing outside `libs/reporting/
  evaluation/canonical/` (and, once built, UEF-2/UEF-3's engine modules)
  may recompute a forward-return, a cost, or an aggregate statistic and
  call it canonical.
- Q100 (see `docs/research/q100_research_and_learning_roadmap.md`) owns
  *what a hypothesis is, what evidence it has accumulated, and what
  lesson that evidence supports*. Q100-2's "Canonical Evidence Mapping"
  **reads** UEF canonical output (Layer 2, in Architecture V2's six-layer
  model — see `docs/architecture/architecture_v2.md` §8); it never
  re-implements a metric calculation of its own.
- Concretely: **Q100 never recomputes UEF metrics.** If Q100-3's
  Reporter/Evaluator needs a WR/PF/MFE/MAE number, it calls UEF-3's
  engine (once it exists) or reads a UEF canonical record's already-
  computed field — it does not carry its own copy of that formula.
- This mirrors, at the research-program scale, the same boundary
  Architecture V2 §4.6 already draws between Operational Truth and
  Knowledge Memory: UEF is authoritative for measurement the way Step5C
  is authoritative for execution; Q100 is advisory/analytical the way the
  Knowledge Vault is, never a second measurement authority competing with
  UEF.

---

## CURRENT AUTHORITATIVE UEF-1 IDENTITY MODEL

**This section, plus the "UEF phase boundary" and "Full UEF roadmap" tables
above, is the single authoritative description of UEF-1's identity model.**
Where anything below this point in the document (including every
"Historical / Superseded Design" section) disagrees with this section, this
section wins. This resolves Codex's `UEF-1 FINAL SCOPE & CONTRACT CLOSURE
AUDIT` H4 finding: §4/§6/§7/§9/§10/§11 further down (the original Work
Package A draft's `EvaluationEpisode`/`market_episode_id`/
`program_episode_id`/minute-bucket design) were left reading as if still
current after Fix2 replaced that design entirely — they are now explicitly
labeled historical, and this section is the one place a reader or a future
audit should trust for "what is the model today."

The current model, defined in
[`identity.py`](../../libs/reporting/evaluation/canonical/identity.py) and
[`record.py`](../../libs/reporting/evaluation/canonical/record.py):

- **`EventRef`** — the single identity primitive reused across all four
  record kinds. Built by `build_event_ref()`.
- **`IdentityKind.NATIVE` / `IdentityKind.DERIVED`** — a source's own stable
  id (`decision_id`/`run_id`/`trade_id`/...) is always preferred
  (`NATIVE`); a typed, canonicalized composite key (`DERIVED`) is used only
  when a source genuinely has none. There is **no minute-bucket, no
  timestamp bucketing of any kind, anywhere in identity** — this was Fix1's
  premise and it was proven wrong (a real Strategist Stage2 artifact showed
  independent decisions landing in the same wall-clock minute) and replaced
  in Fix2, permanently.
- **`canonical_event_id`** — a hash of `(identity_kind, source_namespace,
  source_id, derivation_version)`, all four of which are stored on the
  `EventRef` itself, so `validate_event_ref()` performs true recompute
  validation, not a format check.
- **Derived-identity typed normalization** — every `DERIVED` field is
  tagged with a `DerivedFieldKind` (`SYMBOL`/`TRADING_DATE`/
  `FIXED_CLOCK_LABEL`/`RAW`) and routed through that kind's own
  canonicalization authority before hashing. There is no "raw arbitrary
  dict/value → identity hash" path in the public API; `RAW` is reserved for
  genuinely opaque values (e.g. a numeric epoch) and is rejected outright
  for any field named after a known canonical identity concept (symbol,
  trading_date, clock/fixed_clock, origin, execution_mode,
  observation_type) or for a value that nests one of those field names
  inside it.
- **`evaluation_subject_id`** — `(canonical_event_id, hypothesis_id,
  observation_type)`. Which program/hypothesis evaluates the event, as what
  kind of observation. Excludes `evaluator_version` and `execution_mode`.
- **`evaluation_record_id`** — `(evaluation_subject_id, execution_mode)`.
  The concrete record. `evaluator_version` is provenance-only, never an
  identity input — recomputing the same record under a newer evaluator
  version yields the same `evaluation_record_id` by design.
- **`cross_program_link_key`** — a deliberately non-authoritative grouping
  key (no timestamp parameter at all), never an input to any identity
  function or to `classify_duplicate_relation()`. Two records can share a
  link key while having completely different `canonical_event_id`s; that is
  correct, not a bug.
- **`execution_mode` is evaluation-instance semantics**, not a market-event
  property — the same underlying event can be evaluated once
  `OBSERVATION_ONLY` and once `CONTROLLED_MOCK`, producing two different
  `evaluation_record_id`s that both trace back to the same
  `canonical_event_id`.
- **Native ID uniqueness is a documented contract, not something UEF-1
  verifies at scale.** `NATIVE` identity assumes `(source_namespace,
  source_id)` is event-level unique *within that source namespace* — this
  is a property of the source system UEF-1 trusts, not something this
  package re-derives. Verifying that a specific legacy source's native id
  actually has this property for every historical record is UEF-4's job
  (the adapter layer), not UEF-1's; see the phase boundary table above.
- **Production symbol authority**: `canonicalize_symbol` defers to this
  repo's own `libs.core.symbols.normalize_symbol(..., allow_test_symbols=
  False)` — the same authority every real production symbol consumer in
  this repository uses. `"005930"` and `"A005930"` canonicalize to
  `"005930"`. A short numeric form like `"5930"` is rejected outright, not
  silently accepted as a pseudo-symbol — it is a test/synthetic-symbol
  convention that this repository's own production code never treats as a
  real KRX code, and UEF-1 must not either. A genuine non-KRX pseudo-symbol
  (an index label, a cross-asset cohort label) must contain at least one
  letter (e.g. `"KOSPI200"`, `"BTC-WOORI"`) — a purely numeric string is
  never accepted through the pseudo-symbol path.
- **`AggregateIdentity.canonical_aggregate_id`** is the name every caller
  must use. `AggregateIdentity` reuses `EventRef` internally only as an
  implementation-consistency detail (the same identity primitive backs all
  four record kinds); an aggregate has no market event of its own, and
  nothing about that internal reuse should be read as claiming otherwise.

---

## Closure Reset — response to Codex's `UEF-1A Closure Reset` verdict (CRITICAL:0 HIGH:3 MEDIUM:5 LOW:1, after Fix3's CRITICAL:0 HIGH:4 MEDIUM:4 LOW:1)

Group A — canonical identity/symbol contract:
- **Investigated the actual repository-wide symbol authority** rather
  than assuming: every real artifact read across this entire multi-round
  UEF-1 investigation used exactly 6-digit KRX codes; this repo's own
  production-facing symbol consumers (`kiwoom_portfolio_reader.py`,
  `reporter_analysis.py`, `trade_explain.py`) explicitly call
  `normalize_symbol(..., allow_test_symbols=False)`, which REJECTS a
  short numeric form like `"5930"` outright. **Verdict: Case B** — "5930"
  is a test/synthetic-symbol convention, never a real production
  representation. UEF's `canonicalize_symbol` was already correct as-is
  (it does not zero-pad "5930"); no change was made to it.
- **The actual defect was the generic derived-identity path bypassing
  normalization entirely** — fixed by replacing the raw
  `derived_key_parts: dict[str, Any]` parameter with a typed
  `derived_fields: dict[str, DerivedIdentityPart]`, where every part
  declares a `DerivedFieldKind` (`SYMBOL`/`TRADING_DATE`/
  `FIXED_CLOCK_LABEL`/`RAW`) and is routed through that kind's own
  canonicalization authority before hashing. There is no longer a "raw
  arbitrary dict → identity hash" path anywhere in the public API — `RAW`
  is the only remaining un-normalized kind, and it must be declared
  explicitly rather than reached by omission.

Group B — referential integrity:
- **`RecordLink` split into two validation phases.** Structural (in
  `record.py`, no other record needed): `relation_type` is one of
  `ALLOWED_RECORD_RELATION_TYPES`, `target_record_id` is a well-formed
  `REC_...` id, and a link cannot reference its own record. Referential
  (new `relations.py::validate_record_links(records)`, needs the whole
  collection): for `SUBMISSION_TO_FILL` specifically, the source must
  actually be a `SUBMITTED_INTENT` episode, the target must actually
  exist in the given collection, must actually show confirmed fill
  evidence (`MOCK_FILL`/`BROKER_FILL`), and must match the source's
  symbol and trading_date. Verified against the real 2026-09-10 024060
  submission/fill pair plus every negative case specified (nonexistent
  target, target is another submission, target has no fill evidence,
  target is a different symbol, target is a different trading date).

Group C — Q10 target/cohort identity, pair execution semantics, aggregate naming:
- **Q10 Semiconductor/Index** now share `experiment_id =
  "Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION"` but get distinct
  `hypothesis_id` cohort suffixes (`:SEMICONDUCTOR` / `:INDEX`) — Option A
  of the two the audit offered, matching this program's real research
  design (one experiment, two target cohorts), never distinguished by
  symbol metadata alone.
- **`PairRecord` gained its own `pair_execution_mode`**, independent of
  `left.execution_mode`/`right.execution_mode` — the pair's own
  `evaluation_record_id` no longer depends on which side happens to be
  "left" by construction accident.
- **`AggregateIdentity.canonical_aggregate_id`** (a property over the
  existing `aggregate_ref.canonical_event_id`) is now the name callers
  should actually use — an aggregate has no event, and should not be
  described with event-shaped vocabulary even informally.

See the Closure Reset report delivered alongside this revision for the
full gate-by-gate verdict and updated representability matrix.

---

## Fix3 (superseded by the Closure Reset above) — response to Codex's third REJECT_WORK_PACKAGE_A (CRITICAL:0 HIGH:4 MEDIUM:4 LOW:1)

Fix3 keeps Fix2's architecture (three-layer identity, four-record family)
and closes the remaining defects Codex found within it, without another
redesign:

- **H1 — Aggregate `PARTIAL` lineage validation was actually vacuous.**
  Fix2's boundary check (`0 < coverage < max(episode_count, coverage+1)`)
  could never fail once `coverage > 0`, so `PARTIAL 3/3` and `PARTIAL 4/3`
  both wrongly passed. Rewritten as three hard, mutually exclusive rules
  (`FULL`: `coverage == episode_count`; `PARTIAL`: `0 < coverage <
  episode_count`; `UNKNOWN`: `coverage == 0`), plus `episode_count >= 0`,
  duplicate-id rejection, and an explicit `episode_count == 0` rule
  (only `UNKNOWN` may pair with it). Verified against the exact 9-case
  matrix Codex specified.
- **H2 — Q12's dual horizon families are now read from the real source
  authority**, not a hand-copied tuple: `libs/reporting/baseline_btc_woori_tech/contracts.py::HORIZONS`
  and `HYPOTHESIS_HORIZONS` are imported directly in the test, and every
  overlapping label (`+5m`/`+15m`/`+30m`/`EOD`) gets an independent
  `Checkpoint` entry per `horizon_set_id`, not a single deduplicated
  entry — `+60m` remains the only hypothesis-only label.
- **H3 — Strategist Stage2's fabricated native id removed.** The real
  artifact has exactly one native id for the whole refresh comparison
  (`decision_id`); there is no native id for "the before candidate" or
  "the after candidate" individually. The pair's own event now uses that
  real `decision_id` as `NATIVE`; each side's event is honestly `DERIVED`
  (via the new typed `build_derived_event_ref`, keyed on `decision_id` +
  side + the side's own symbol).
- **H4 — Typed derived-identity builders** (`build_derived_event_ref`,
  `build_fixed_clock_event_ref`) canonicalize `trading_date`/`symbol`/
  `fixed_clock_label` (via `canonicalize_fixed_clock_label`, new: `"09:00"`
  and `"09:00:00"` now normalize identically) BEFORE hashing, closing the
  gap where the generic `derived_key_parts` dict hashed whatever raw
  value it was given (so `"005930"` vs. `"A005930"` used to produce
  different derived ids). The generic path is kept for genuinely
  non-date/symbol derived fields (e.g. Q12's `target_epoch`) but is no
  longer used for Q10's fixed-clock identity, which now goes through the
  typed builder.
- **M1 — Canonical symbol storage enforced on the record itself**, not
  only inside identity: `EpisodeRecord`/`PairSide`/`SequenceRecord`
  `__post_init__` now reject a non-canonical `symbol` value outright
  (e.g. `"A005930"`), and every builder (`build_episode_record`,
  `build_sequence_record`) canonicalizes before constructing.
- **M2 — Sequence leg validation strengthened**: unique `leg_id`, unique
  positive strictly-increasing `order_index`, `parent_leg_id` must
  reference an actual leg in the same sequence and must precede its
  child (no self-parent, no "future" parent), and a leg with no parent
  may not simultaneously declare a real `relation_to_previous`. Verified
  against both a real 2-leg and a real 3-leg `same_symbol_sequences`
  artifact.
- **M3 — Checkpoint provenance validation extended** beyond `gross_return`
  to `net_return`/`mfe`/`mae` — any of the four outcome fields present on
  an `OBSERVED` checkpoint now requires `observed_price`, unless the new
  `CheckpointMetricKind.AGGREGATE_ONLY` escape hatch is explicitly
  declared.
- **M4 — `RecordLink`** gives a submission record an explicit,
  non-identity-affecting `SUBMISSION_TO_FILL` relation to its later,
  separately-identified fill record (`ALLOWED_RECORD_RELATION_TYPES` is
  the single authoritative, deliberately small set — kept as a frozenset
  constant, not an Enum, so it can grow without an enum-explosion review
  each time, but never through an ad hoc unvalidated string).
- **L1 — `AggregateIdentity.aggregate_event` renamed to `aggregate_ref`**
  so it no longer reads as if it were a market event (an aggregate has
  none).

See the Fix3 report delivered alongside this revision for the full
gate-by-gate verdict, the complete real-legacy-roundtrip matrix, and the
self-assessed severity counts.

---

## Fix2 (superseded by Fix3 above) — response to Codex's second REJECT_WORK_PACKAGE_A (CRITICAL:0 HIGH:5 MEDIUM:5 LOW:1)

Fix2 abandons Fix1's identity premise entirely rather than patching it.
Fix1's `market_event_id = date + symbol + event_origin + minute-bucket`
was proven wrong by a real artifact: `strategist_stage2_authority_review.json`
shows Strategist Stage2 polling roughly every 30 seconds, so two
genuinely independent decisions (different `decision_id`, different
`run_id`) routinely land in the same wall-clock minute for the same
symbol — Fix1's bucket would have silently merged them.

**New identity model** (`identity.py`): every event now gets an
`EventRef`, built by `build_event_ref()` with a strict priority order —
(1) the source's own **NATIVE** stable id (`decision_id`/`run_id`/
`trade_id`/`signal_id`/`candidate_id`/`submission_id`/`cohort_id`/
`episode_id`) is always preferred; (2) a **DERIVED** composite key is
used only when a source genuinely has none (e.g. Q10 lead-market's
fixed-clock checkpoints). No timestamp bucketing participates in
identity at all any more. `canonical_event_id` is a hash of
`(identity_kind, source_namespace, source_id, derivation_version)` —
critically, all four inputs are stored ON the `EventRef` itself, so
`validate_event_ref()` performs **true recompute validation**, not a
prefix/format check.

**Cross-program linkage separated from identity** (`cross_program_link_key`):
a deliberately non-authoritative grouping key with no timestamp parameter
at all (so it structurally cannot slide back into being an identity
mechanism) — two records can share a link key while having completely
different `canonical_event_id`s, which is the correct, intended outcome.
`classify_duplicate_relation()`'s signature excludes it entirely.

**Record-family-specific identity** (`record.py`): each of the four
record kinds now has its own identity shape instead of sharing one flat
episode identity — `PairIdentity` carries three separate `EventRef`s
(the pair's own event, plus an independent `left_event`/`right_event`
each, since a real Stage2 record has before/after candidates on
genuinely different symbols with their own native decision context);
`SequenceIdentity` + `SequenceLeg` (each leg carries its own `EventRef`,
`order_index`, `parent_leg_id`, `relation_to_previous`); `AggregateIdentity`
(never requires a symbol/trading_date — an aggregate has no market event
of its own).

**Other Fix2 closures**: `LineageStatus` (FULL/PARTIAL/UNKNOWN) replaces
the boolean `source_lineage_known`, with internal-consistency validation
against `episode_count`; `EventDateRelation` makes the entry-timestamp-
vs-trading_date relationship explicit and validated (same-day is the
default and is checked against the real timestamp, not just assumed);
`normalize_enum_value()` fixes a confirmed real defect
(`str(EventOrigin.CANDIDATE)` returns `"EventOrigin.CANDIDATE"`, not
`"CANDIDATE"`, on this Python version — verified empirically); a new
`EntryAuthority.SUBMITTED_INTENT` value distinguishes "an order was
submitted" from "an order was filled," fixing a real mislabeling Codex
found in the Opening Controlled Probe roundtrip (a bare
`probe_submissions.json` row has no confirmed fill evidence and must
never be represented as `MOCK_FILL`); `Checkpoint.horizon_set_id`
preserves Q12's own two disagreeing horizon families (`HORIZONS` vs.
`HYPOTHESIS_HORIZONS`) distinctly rather than flattening them; a real
2-leg (and larger) `same_symbol_sequences` artifact is now required and
used for the sequence-fidelity test, not a single-leg fixture.

See the Fix2 report delivered alongside this revision for the full
gate-by-gate verdict and the complete real-legacy-roundtrip matrix.

---

## Fix1 (superseded by Fix2 above) — response to Codex's first REJECT_WORK_PACKAGE_A

Codex's independent audit of the original Work Package A draft returned
`REJECT_WORK_PACKAGE_A` (CRITICAL:0, HIGH:7, MEDIUM:6, LOW:1). Only
**G5 (additive / no runtime change)** was approved as-is; G0–G4 had to be
re-proven. This revision replaces the rejected two-layer, freely-hashed
identity and single-`EvaluationEpisode` design with:

1. **A three-layer identity model** (`market_event_id` →
   `evaluation_subject_id` → `evaluation_record_id`), with
   `evaluator_version` and `execution_mode` both excluded from identity
   inputs entirely (HIGH-1/2/3) and a real **timestamp normalization
   contract** (minute-bucketed epoch seconds, `Asia/Seoul`-assumed naive
   input, discrete labels for `FIXED_CLOCK`) replacing the
   one-second-jitter-sensitive exact-timestamp hash.
2. **Structured canonical JSON hashing** (`identity._canonical_json_bytes`)
   replacing the collision-prone `"|".join(...)` scheme (HIGH's stable-hash
   finding).
3. **A four-record tagged union** (`EpisodeRecord`, `PairRecord`,
   `SequenceRecord`, `AggregateRecord`) replacing the single
   `EvaluationEpisode`, so paired comparisons (Stage2's real R1-vs-R2 data
   confirms the two sides can be **different symbols**), multi-leg
   sequences, and pre-aggregated statistics each get a shape that actually
   fits them (HIGH-5).
4. **`DuplicateRelation` extended** with `DIFFERENT_SYMBOL` (a real defect:
   the rejected classifier mis-labeled a different-symbol pair as
   `SAME_SYMBOL_DIFFERENT_EPISODE`) and two new relations that make actual
   use of the previously-dead `evaluator_version_a/b` parameters.
5. **`SampleStatus`/`EvidenceStatus` re-separated** (`INSUFFICIENT_EVIDENCE`
   removed from `SampleStatus`) and **`ResearchStatus` removed from the
   record family entirely** (kept only as shared vocabulary).
6. **Checkpoint-level `horizon_origin`**, now authoritative and able to
   mix origins within one record; **optional `entry`**; new **`exit`**
   subrecord; explicit **`ReturnUnit`** convention
   (`PERCENTAGE_POINTS`, matching this codebase's existing convention
   everywhere `_pct` fields appear).
7. **Explicit, non-silent JSON-safe serialization** — an unsupported type
   (e.g. `datetime`) now raises `CanonicalSerializationError` naming the
   offending field, rather than crashing deep inside `json.dumps`.
8. **Real legacy artifact roundtrip tests** — every one of the 12+
   families is now tested by opening an actual generated file under
   `reports/`/`data/logs/` and mapping a real row, not a hand-typed
   fixture (see `tests/test_uef1_work_package_a_canonical_contract.py`).

See the Fix1 report delivered alongside this revision for the full
gate-by-gate verdict.

---

## 1. Problem statement

The 2026-09-12 [Unified Evaluation Framework Integrity Review](unified_evaluation_framework_integrity_review.md)
found that Q9–Q18, Opening Alpha, and the Alpha Research Board share a
strategic goal (measure many independent hypotheses fairly, on one shared
axis, accumulated linearly over time) but not the machinery to do it:

- 22 distinct evaluation surfaces, using at least 7 structurally different
  observation units.
- 16 independently-written calculation functions (10 forward-checkpoint
  engines, 6 aggregate-statistics engines), with a genuine type-incompatible
  divergence in profit-factor's zero-loss convention (`999.0` float vs.
  `"INF"` string).
- At least 5 different literal "live cost" percentages in simultaneous use.
- The same horizon label (`+30m`) meaning three structurally different
  things depending on which module wrote it (candidate-baseline-anchored,
  actual-exit-anchored, or a fixed KST clock time).
- The Alpha Research Board itself provably double-counting the same
  underlying episode across multiple candidate rows, with no mechanism to
  detect it.

UEF-1's goal is **not** to force every strategy/hypothesis into one shape,
and **not** to replace any existing calculation. It is to give every
evaluation program a shared *language* — so that when two programs measure
the same real event, or use the same horizon word, or apply a cost model,
that can be stated unambiguously, without changing what any of them
currently compute.

## 2. Current-state evidence

See the integrity review linked above for the full inventory, tables, and
citations. The load-bearing facts this design responds to directly:

- **Episode ≠ Trade ≠ Signal ≠ Candidate** — confirmed by the review's
  observation-unit table (§3 there): candidate/signal event, trade, day,
  paired before/after delta, pre-aggregated statistic, blocked episode,
  and day-symbol sequence are all genuinely different things currently
  called "N" somewhere in this codebase.
- **Two structurally separate forward-checkpoint families exist**
  ("Family A": candidate/signal-baseline-anchored; "Family B":
  actual-exit-anchored), sharing horizon *labels* but not a base
  timestamp, a calculation function, or (for Family B) any cost model.
- **The Alpha Research Board is a mixed calculator/aggregator**, not a
  passive display layer, and its own code comments (`canonical.py`)
  document three successive patches after repeatedly discovering that a
  single `status` field was conflating operational status, fixed-window
  validation verdict, and production-promotion eligibility.
- **Legacy program identifiers (`PROGRAM_ID`, `COHORT_ID`, `trade_id`,
  `signal_id`, `run_id`) are load-bearing** — they are cited by name across
  dozens of historical closure/audit documents and must not be silently
  reinterpreted or dropped by any future unification effort.

## 3. Canonical terminology

Defined in [`libs/reporting/evaluation/canonical/contracts.py`](../../libs/reporting/evaluation/canonical/contracts.py).

### 3.1 `ObservationType`

What concrete shape one `EvaluationEpisode` has:
`SIGNAL, CANDIDATE, RANK_EVENT, ENTRY_OPPORTUNITY, BLOCKED_OPPORTUNITY,
SHADOW_ENTRY, CONTROLLED_ENTRY, ACTUAL_TRADE, EXIT_EVENT, DAY_SYMBOL,
PAIRED_DECISION, AGGREGATE_SOURCE`.

Every one of the 22 evaluation surfaces reviewed maps onto exactly one of
these without forcing a stretch (see §11, the lossless representation
matrix).

### 3.2 `EventOrigin`

What real-world event an episode's timestamps are anchored to — this is
the single enum that makes the Family-A/Family-B/fixed-clock distinction
explicit instead of implicit in prose, and is reused for both the
episode's own origin and its `horizon_origin` (deliberately one enum, not
two, to avoid an unnecessary duplicate axis):
`SIGNAL, CANDIDATE, MONITOR_DECISION, ENTRY, ACTUAL_FILL, ACTUAL_EXIT,
OPEN, FIXED_CLOCK, CUSTOM`.

### 3.3 `EntryAuthority`

Where an episode's entry price/time actually came from:
`SIGNAL_PRICE, CANDIDATE_PRICE, SCANNER_REFERENCE, MONITOR_REFERENCE,
MARKET_QUOTE, BEST_ASK, SIMULATED_FILL, MOCK_FILL, BROKER_FILL, OPEN_PRICE,
FIXED_CLOCK_PRICE`.

### 3.4 `ExecutionMode`

What actually happened (or could happen) at the broker:
`OBSERVATION_ONLY, SHADOW, CONTROLLED_MOCK, BROKER_LIVE, DIAGNOSTIC`.

### 3.5 Three separate status axes (the direct fix for the Board's own documented conflation)

- **`SampleStatus`** — per-episode data completeness (did *this* episode's
  own data arrive intact?): `ELIGIBLE, COMPLETE, PARTIAL, INCOMPLETE,
  INSUFFICIENT_EVIDENCE, EXCLUDED, CONTAMINATED, DUPLICATE`.
- **`EvidenceStatus`** — statistical/validation maturity of the
  *accumulated* evidence: `INSUFFICIENT, COLLECTING, SUFFICIENT,
  CONFLICTED`.
- **`ResearchStatus`** — the hypothesis/program's own lifecycle, a property
  of the program surfaced onto episodes for convenience:
  `PROSPECTIVE, VALIDATING, RETAIN, DEPRECATE_REVIEW, CLOSED`.

`sample_status = COMPLETE` and `research_status = PROSPECTIVE` are
independent facts that can and do coexist — exactly the distinction the
Board's own `canonical.py` comments describe having to retrofit after the
fact (`operation_status`/`fixed_validation_status`/
`production_promotion_status`). UEF-1 makes this a first-class design
decision from the start instead of a later patch.

### 3.6 `CheckpointCompleteness`

A finer granularity than `SampleStatus`: one episode can have some
checkpoints `OBSERVED` and others still `PENDING`/`STALE`/`PARTIAL`/`MISSING`.

## 4. `EvaluationEpisode` schema (HISTORICAL — SUPERSEDED, see "CURRENT AUTHORITATIVE UEF-1 IDENTITY MODEL" above)

**This section describes the original Fix1 draft schema, replaced by the
four-record family (`EpisodeRecord`/`PairRecord`/`SequenceRecord`/
`AggregateRecord`) starting with Fix2. It is kept only as a historical
record of the design process and must not be read as describing the
current schema.** For the current schema, see `record.py` directly and
the "CURRENT AUTHORITATIVE UEF-1 IDENTITY MODEL" section above.

Defined in [`libs/reporting/evaluation/canonical/record.py`](../../libs/reporting/evaluation/canonical/record.py),
as a tree of frozen dataclasses matching the requested structure exactly:

```
EvaluationEpisode
├─ schema_version, evaluator_version
├─ identity: EpisodeIdentity
│    episode_id, experiment_id, hypothesis_id, source_run_id,
│    source_record_id, market_episode_id, program_episode_id
├─ subject: EpisodeSubject
│    trading_date, symbol, side, observation_type, execution_mode
├─ origin: EpisodeOrigin
│    entry_authority, horizon_origin, signal_time, candidate_time,
│    entry_time, entry_price
├─ checkpoints: tuple[Checkpoint, ...]
│    horizon_label, target_timestamp, observed_timestamp, observed_price,
│    gross_return, net_return, mfe, mae, completeness, source
├─ cost: EvaluationCost
│    cost_profile_id, applied_cost
├─ quality: EvaluationQuality
│    sample_status, evidence_status, contaminated, exclusion_reason,
│    completeness
├─ provenance: Provenance
│    legacy_program, legacy_schema, source_artifact, source_function
├─ research_status: ResearchStatus | None   (kept separate from `quality`, see §3.5)
└─ metadata: Mapping[str, Any]              (namespaced per program, see §5)
```

`to_dict()`/`from_dict()` provide lossless JSON-safe serialization
(enums become their string values; round-trip is tested in §12).

**Deliberately not implemented here**: no function anywhere in this
package computes `gross_return`, `net_return`, `mfe`, `mae`, or any
aggregate statistic from raw price data. The record can *carry* a value a
Work-Package-B engine (or, until then, a legacy adapter) computed; it
never produces one itself.

### 4.1 Validation scope

`__post_init__` rejects only unambiguously self-contradictory shapes:
`OBSERVATION_ONLY`/`SHADOW` execution mode paired with `BROKER_FILL` (or,
for `OBSERVATION_ONLY`, `MOCK_FILL`) entry authority — an
observation/shadow episode cannot claim an authoritative real or mock
fill occurred, by definition. `DIAGNOSTIC` mode is deliberately
unrestricted, since a diagnostic episode legitimately analyzes an
already-real trade after the fact (e.g. Q13/Q14 scoring a genuine broker
fill). This is intentionally a thin data contract, not a policy engine —
no minimum-sample, promotion-gate, or program-specific business rule lives
here; those remain each program's own authority.

## 5. Extension metadata

Program-specific fields never enter the core schema. They live in
`metadata`, namespaced per program (`metadata["q12"]`, `metadata["q10"]`,
`metadata["opening"]`, `metadata["stage2"]`, ...) exactly as specified —
e.g. Q12's `btc_return_24h`/`btc_regime`, Q10's `reaction_class`, Opening's
`scanner_rank`/`wait_reason`. This keeps the core schema strategy-neutral
while losing nothing.

## 6. Episode identity (HISTORICAL — SUPERSEDED, see "CURRENT AUTHORITATIVE UEF-1 IDENTITY MODEL" above)

**This section describes the original Fix1 two-layer
`market_episode_id`/`program_episode_id` identity model, replaced in Fix2
by the `EventRef`-based `NATIVE`/`DERIVED` model (`canonical_event_id` →
`evaluation_subject_id` → `evaluation_record_id`) because a real
Strategist Stage2 artifact proved the minute-bucket premise below wrong.
Kept only as a historical record; do not use `market_episode_id` or
`program_episode_id` in new code — neither exists in `identity.py` any
more.**

Defined in [`libs/reporting/evaluation/canonical/identity.py`](../../libs/reporting/evaluation/canonical/identity.py).
**Two layers, adopted deliberately** (not collapsed into one) — see §7 for
why.

- **`market_episode_id`** — identifies the underlying real-world event,
  independent of which program/hypothesis evaluates it. Deterministic
  hash of `(trading_date, symbol, event_origin, event_timestamp,
  setup_identity)`. `setup_identity` is an explicit escape hatch for the
  rare case where the same symbol/day/origin/timestamp genuinely contains
  more than one independent setup; ordinary callers leave it empty and
  rely on the timestamp alone — never on "date + symbol" by itself, which
  the specification explicitly calls out as insufficient (one symbol can
  have many setups in one day).
- **`program_episode_id`** — identifies this evaluation record within its
  own evaluating program/hypothesis. Deterministic hash of
  `(market_episode_id, hypothesis_id, observation_type, execution_mode,
  evaluator_version)`. This becomes a record's `identity.episode_id`.

Both are `sha256`-based (20 hex chars, prefixed `MKT_`/`PRG_` for
human-debuggability), so they are deterministic, restart-independent, and
collision-resistant — never a counter, timestamp-of-computation, or random
value.

## 7. Why this identity model (HISTORICAL — SUPERSEDED, see "CURRENT AUTHORITATIVE UEF-1 IDENTITY MODEL" above)

**This section justifies the superseded two-layer `market_episode_id`/
`program_episode_id` design from §6. The reasoning that a duplicate/overlap
classifier needs two identity layers is still correct, but the concrete
mechanism described here is not — Fix2's `EventRef` (`NATIVE`/`DERIVED`) +
`evaluation_subject_id`/`evaluation_record_id` is the current mechanism,
and `classify_duplicate_relation()`'s actual signature (in `identity.py`)
is the authoritative reference, not the table below.**

The integrity review's single most concrete, reproducible finding was that
the Alpha Research Board's `IMMEDIATE_OPENING_PROBE`, `CONFIRMED_RECURRENT_RANK`,
`DISLOCATION_REBOUND`, `OPEN_0_20_RANK1_30M`, and `R1_SCANNER_RISK_HIGH_30M_V1`
rows all provably read from the **same** underlying episode population
(`opening_rank1_shadow_cumulative.json`), with **no code anywhere** that
could tell you so — because the existing system has exactly one identity
concept (whatever ad hoc id each program happens to assign), conflating
"the same real event" with "this program's record of it."

A single flat `episode_id` cannot express "these five Board rows are
counting the same episode five times" without either (a) forcing every
program to agree on one id scheme up front (which would break every
existing artifact's own id), or (b) losing the information entirely. The
two-layer split solves this without touching any existing program's own
id: `market_episode_id` gives every consumer (a future Work-Package-B
aggregator, or the Board itself) a mechanical way to ask "have I already
counted this real event under a different hypothesis?" while
`program_episode_id`/`identity.episode_id` remains exactly the kind of
per-record id every program already has one of.

The alternative (one identity layer only) was rejected specifically
because it cannot represent §16 of the task spec's requirement — "same
episode_id + different hypothesis is normal; same episode_id + same
hypothesis + same evaluator version is a duplicate" — without conflating
the two questions "is this the same real event?" and "is this the same
evaluation of it?" into one field, which is precisely the class of bug
this whole review exists to prevent.

`classify_duplicate_relation()` uses both layers to answer exactly that:

| market_episode_id | program_episode_id | hypothesis | → |
|---|---|---|---|
| same | same | same | `ACCIDENTAL_DUPLICATE` |
| same | different | different | `LEGITIMATE_MULTI_HYPOTHESIS` |
| different, same symbol | — | same | `REPEATED_SETUP` |
| different, same symbol | — | different | `SAME_SYMBOL_DIFFERENT_EPISODE` |

This is a pure classification helper — it does not filter, drop, or
otherwise change any record; a consumer decides what to do with a flagged
`ACCIDENTAL_DUPLICATE`.

## 8. Legacy ID preservation

Nothing about `PROGRAM_ID`, `COHORT_ID`, `trade_id`, `signal_id`,
`candidate_id`, or `run_id` is replaced. `Provenance.legacy_program` /
`legacy_schema` / `source_artifact` / `source_function` and
`EpisodeIdentity.source_run_id` / `source_record_id` exist specifically to
carry every one of those forward untouched. The lossless-representation
tests in §12 verify this for every legacy family reviewed.

## 9. Versioning (HISTORICAL — SUPERSEDED version string; the point about `evaluator_version` still holds)

**`SCHEMA_VERSION` is no longer `"uef1_evaluation_episode.v1"` — the
current value, defined in `contracts.py`, is
`SCHEMA_VERSION = "uef1_evaluation_record.v3"`, carried on every record's
own `schema_version` field.** The remaining point below (`evaluator_version`
as a free provenance field, not an identity input) is still accurate.

`evaluator_version` is a free field on the record, ready for Work Package
B to populate once a canonical forward-return/cost/metric engine exists —
no engine is implemented yet, but the field exists so that day-one records
don't need a schema migration to carry it.

## 10. File placement (HISTORICAL — SUPERSEDED file/module description, see "CURRENT AUTHORITATIVE UEF-1 IDENTITY MODEL" above)

**The file tree below describes the original Fix1 layout
(`record.py -- EvaluationEpisode`, `identity.py -- market_episode_id /
program_episode_id`). The actual current layout is unchanged in
location but not in content**: `record.py` now defines `EpisodeRecord`/
`PairRecord`/`SequenceRecord`/`AggregateRecord` and their builders;
`identity.py` now defines `EventRef`/`build_event_ref`/
`evaluation_subject_id`/`evaluation_record_id`/`cross_program_link_key`;
and a `relations.py` module (added in the Closure Reset, not shown below)
now owns collection-level referential validation
(`validate_record_links`).

`libs/reporting/evaluation/canonical/` was chosen over a new top-level
package because:

- `libs/reporting/evaluation/` already hosts the closest thing to a
  cross-cutting evaluation contract in this repo today
  (`libs/reporting/evaluation/contracts.py`, `CONTRACT_VERSION =
  "q9_evaluation_contract.v1"`, using the exact same `class X(str, Enum)`
  pattern this design follows) — this is the natural, already-established
  location for evaluation-wide contracts, not a novel one.
- A new top-level `libs/evaluation/` package would fragment that
  precedent rather than build on it, with no offsetting benefit.
- `canonical/` as a subpackage (not a same-level module) avoids any name
  collision with the existing `contracts.py`, which is Q8/Q9-specific and
  unrelated to this cross-program schema.

```
libs/reporting/evaluation/canonical/
├─ __init__.py       -- public API surface
├─ contracts.py       -- enums + SCHEMA_VERSION
├─ record.py          -- EvaluationEpisode and its nested dataclasses
└─ identity.py         -- market_episode_id / program_episode_id / classify_duplicate_relation
tests/test_uef1_work_package_a_canonical_contract.py
docs/research/unified_evaluation_foundation.md   (this document)
```

## 11. Lossless representation matrix (HISTORICAL table wording — the underlying representability claim is CURRENT and re-verified)

**The table below still names the mapping decisions accurately at a
conceptual level (which `ObservationType`/`EventOrigin`/`EntryAuthority`
each legacy family maps to), but it was written against the superseded
`EvaluationEpisode` schema and its own header sentence below is stale (the
real, current proof lives in `EpisodeRecord`/`PairRecord`/`SequenceRecord`/
`AggregateRecord` construction tests, not an `EvaluationEpisode` fixture).
Treat `tests/test_uef1_work_package_a_canonical_contract.py`'s actual
12-family roundtrip tests as the authoritative, currently-passing proof —
this table is a historical index into that same conclusion, not an
independent claim.**

Each row below has a corresponding fixture test in
`tests/test_uef1_work_package_a_canonical_contract.py` that builds an
`EvaluationEpisode` from a literal shape taken from that program's real
output, and asserts the load-bearing fields survive: identity, symbol,
timestamp semantics, observation type, entry authority, horizon origin,
execution mode, sample/evidence status, legacy provenance, and
strategy-specific metadata.

| Legacy evaluation | Representable? | Key mapping decisions |
|---|---|---|
| Q10 Semiconductor (lead-market, stock target) | PASS | `EventOrigin.FIXED_CLOCK`, `EntryAuthority.FIXED_CLOCK_PRICE`, `ObservationType.DAY_SYMBOL`; `reaction_class` in `metadata["q10"]` |
| Q10 Index (lead-market, index target) | PASS | same as above with `metadata["q10"]["target_kind"]="index"` |
| Q11 (Opportunity Engine) | PASS | `ObservationType.SHADOW_ENTRY`, `ExecutionMode.SHADOW`, `EntryAuthority.SIMULATED_FILL`, `EventOrigin.SIGNAL`; legacy `trade_id` in `identity.source_record_id` |
| Q12 (BTC-Woori) | PASS | `ObservationType.CANDIDATE`, `ExecutionMode.DIAGNOSTIC`; `btc_return_24h`/`btc_regime` in `metadata["q12"]` |
| Opening Rank1 Shadow | PASS | `ObservationType.RANK_EVENT`, `ExecutionMode.OBSERVATION_ONLY`, `EntryAuthority.SCANNER_REFERENCE`; `scanner_rank` in `metadata["opening"]` |
| Opening Controlled Probe | PASS | `ObservationType.CONTROLLED_ENTRY`, `ExecutionMode.CONTROLLED_MOCK`, `EntryAuthority.MOCK_FILL`; `wait_reason`/`opening_probe_type` in `metadata["opening"]` |
| Short Alpha Discriminator | PASS | `ObservationType.AGGREGATE_SOURCE`, `ExecutionMode.OBSERVATION_ONLY` |
| Strategist Stage2 Effectiveness | PASS | `ObservationType.PAIRED_DECISION` (before/after role and `decision_id` carried in `metadata["stage2"]`, since the canonical core does not compute a paired delta itself) |
| No-Trade Attribution | PASS | `ObservationType.BLOCKED_OPPORTUNITY`, `quality.sample_status=EXCLUDED`; day-level and episode-level variants both fit the same shape with different `symbol`/`metadata` |
| Horizon/Exit Evaluation | PASS | `ObservationType.ACTUAL_TRADE`, `ExecutionMode.BROKER_LIVE`, `EntryAuthority.BROKER_FILL`, `EventOrigin.ACTUAL_EXIT`; `cost.applied_cost=None` faithfully represents that Family B carries no cost model of its own |
| Same-Symbol Sequence | PASS | `ObservationType.ACTUAL_TRADE`; `trade_ordinal`/`day_symbol_sequence_id` in `metadata["same_symbol_sequence"]`; `setup_identity="ordinal=N"` disambiguates same-day same-symbol trades |
| Q13 / Q14 | PASS | Both `ObservationType.ACTUAL_TRADE` + `ExecutionMode.DIAGNOSTIC`; scores/root-cause carried in `metadata["q13"]`/`metadata["q14"]` since neither is a return metric; same underlying trade correctly yields the same `market_episode_id` and different `program_episode_id` per hypothesis |
| Alpha Board candidate | PASS | `ObservationType.AGGREGATE_SOURCE` + `research_status=VALIDATING`, demonstrating the separate `research_status` axis alongside per-episode `quality` |

```
LOSSLESS REPRESENTATION: 13/13 PASS (Q13 and Q14 counted together as one row above; individually 12 distinct named groups + Alpha Board candidate, matching the 12 groups the task specified plus the Board row)
```

## 12. Semantic collision handling

Three explicit tests confirm the schema disambiguates cases that look
identical by label alone:

- `test_fixed_clock_horizon_distinguished_from_entry_anchored_horizon` —
  Q10's fixed-clock `"09:30"` vs. an entry-anchored `"+30m"` differ in
  `horizon_origin` (`FIXED_CLOCK` vs. `ENTRY`), never collapsing to the
  same meaning just because both nominally mean "30 minutes."
- `test_post_exit_horizon_distinguished_from_candidate_baseline_horizon` —
  Family A (candidate-baseline) vs. Family B (actual-exit) differ in both
  `horizon_origin` and `observation_type`.
- `test_simulated_entry_distinguished_from_controlled_mock_fill` — Q11's
  own simulated fill vs. Opening Alpha's controlled mock fill differ in
  both `entry_authority` and `execution_mode`.

Additional identity-level collision tests confirm "signal N vs. trade N"
and "same market episode vs. different hypothesis evaluation" are
distinguishable without ambiguity (§13).

## 13. Non-goals (explicit Work Package B boundary)

Not implemented in this Work Package, by design:

- Canonical forward-return formula / checkpoint resolver.
- Canonical missing-data / delay tolerance policy.
- Canonical cost profile(s).
- Canonical net return, MFE, MAE calculation.
- Canonical WR/PF/Avg aggregator.
- Any migration of an existing evaluator to write to this schema.
- Any change to the Alpha Research Board's own calculation, threshold, or
  display logic.
- Q100, or any new Q-numbered program.

## 14. Production safety

Additive only. No existing file was modified except this document's own
sibling links (none — this is a new document) and the git-tracked-but-
unrelated `docs/en/12_roadmap.md`/`docs/architecture/architecture_v2.md`
already sitting uncommitted from a prior, separate session (not touched by
this Work Package). `libs/reporting/evaluation/canonical/` is not imported
by any existing module. Existing runtime output, report output, and
calculations are unchanged — confirmed by running the full pre-existing
evaluation-adjacent test surface (413 tests across Q9–Q18, Opening Alpha,
Alpha Research Board, and diagnostics) after adding this package: **413
passed, 0 failed**, and the full 3181-test suite still collects cleanly
with no naming collisions.
