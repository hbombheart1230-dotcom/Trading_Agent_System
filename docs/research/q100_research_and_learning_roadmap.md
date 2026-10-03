# Q100 — Alpha Research & Learning Program (Design Only)

Status: **DESIGN STAGE — NOT IMPLEMENTED**
Scope: documentation and design proposal only. No code, runtime, strategy,
prompt, evaluation-logic, or execution-logic change accompanies this
document. No commit, no push.

This document defines Q100-1 through Q100-6: the program that turns UEF
canonical evaluation output (see
[`unified_evaluation_foundation.md`](unified_evaluation_foundation.md))
into accumulated research evidence and, eventually, retrievable strategy
knowledge — without ever becoming a second measurement authority (see the
"UEF / Q100 dependency" section of that document) and without any
production strategy auto-modification.

Q100 sits at Layer 5 (Reasoning/Learning) of Architecture V2's six-layer
model — see
[`docs/architecture/architecture_v2.md`](../architecture/architecture_v2.md)
§8.

---

## 1. Why "Q100" and not "Q19, Q20, ..."

Q9 through Q18 (plus Opening Alpha and the Alpha Research Board) are each
individual hypotheses/programs. Q100 is not another hypothesis in that
sequence — it is the *research and learning infrastructure* that Q9-Q18
and every future Q-numbered program run inside of. It is named distinctly
(100, not the next sequential number) precisely so it is never mistaken
for "just one more strategy hypothesis."

## 2. Relationship to UEF

Q100 depends on UEF but is never UEF. Concretely:

- Q100-2 (Canonical Evidence Mapping) requires UEF-3 (canonical cost &
  metric engine) to exist before it can map real evidence with trustworthy
  numbers — until then, Q100 design work (registry schema, evidence-
  mapping schema) may proceed, but Q100 execution against live canonical
  metrics does not (see the priority tiers in `docs/en/12_roadmap.md`).
- Q100-4/Q100-5 (Knowledge & Memory Layer, Retrieval Layer) depend on
  Architecture V2's Experience/Memory Layer design (§4.5-§4.9 there) for
  their record shapes.
- Q100 never recomputes a UEF metric. See the dependency statement in
  `unified_evaluation_foundation.md`.

## 3. Q100-1 — Research Program Registry

A registry of every hypothesis/program (Q9-Q18, Opening Alpha, Alpha
Board, and future ones), so "which programs exist and what is each one's
current lifecycle state" stops being answerable only by reading prose
across dozens of daily-patch documents.

Registry categories (conceptual fields, not implemented):

```
ProgramEntry
  program_id            -- e.g. "Q10", "OPENING_ALPHA", "ALPHA_BOARD"
  title
  hypothesis_summary
  research_status       -- reuses UEF's ResearchStatus vocabulary:
                            PROSPECTIVE / VALIDATING / RETAIN /
                            DEPRECATE_REVIEW / CLOSED
  owner_docs            -- pointers into docs/daily_patch/, docs/evaluation/
  first_observed_date
  last_updated_date
  target_cohorts        -- e.g. Q10's SEMICONDUCTOR / INDEX split
  related_programs      -- e.g. Opening Alpha <-> Q11 overlap (MEDIUM,
                            per docs/research/q11_opening_alpha_current_state_review.md)
```

Status: **DESIGN ONLY.** No registry file/table exists yet.

## 4. Q100-2 — Canonical Evidence Mapping

Maps each `ProgramEntry` to its accumulated UEF canonical evidence
(`EpisodeRecord`/`PairRecord`/`SequenceRecord`/`AggregateRecord` instances
whose `hypothesis_id` belongs to that program), producing a rolled-up
`StrategyEvidence` view (the same conceptual schema Architecture V2 §4.8
already names) — never a second copy of the underlying metric
calculation, only a read/aggregation over what UEF-3/UEF-4 already
produced.

Status: **DESIGN ONLY.** Depends on UEF-3/UEF-4 for real numbers; the
mapping schema itself may be drafted earlier.

## 5. Q100-3 — Reporter / Evaluator (structured attribution model)

Extends Reporter's existing daily/weekly/monthly evaluation (Architecture
V2 §4.10) with structured, per-program attribution: for a given program
and time window, what fraction of outcome variance traces to entry
timing, exit timing, market regime, or execution slippage — a
*structured attribution*, not a free-text summary. This is Reporter's
Q100-facing role; it is the same Reporter role, not a new agent.

Status: **DESIGN ONLY.**

## 6. Q100-4 — Knowledge & Memory Layer (4-tier structure)

Restates Architecture V2's memory boundary (§4.6) as Q100's own operating
constraint, in four tiers:

```
Tier 1  Operational Truth     data/, SQLite, EventLog, chronicles
                               NEVER migrated into the Knowledge Vault
Tier 2  Evaluation Truth      UEF canonical records + reports built from them
Tier 3  Knowledge             docs/ + validated memory (promoted lessons)
Tier 4  Knowledge UI          Obsidian — view only, never authority
```

This is identical in substance to Architecture V2 §8's six-layer model's
Layers 1-4; Q100 uses the same four tiers because Q100 is a Layer-5
consumer of exactly those layers, not a parallel hierarchy.

### 6.1 Memory provenance — required fields

Every promoted memory entry (an `ExperienceRecord`/`Lesson`, per
Architecture V2 §4.8-§4.9) must carry, at minimum:

```
source_program_id        -- which Q-program this traces to
source_evaluation_record_id  -- the UEF canonical record(s) this was
                                 promoted from (never a raw event directly)
promotion_stage          -- Raw Event / Daily Observation / Repeated
                             Evidence / Finding / Lesson / Strategy
                             Knowledge (per Architecture V2 §4.9)
promoted_by              -- "reporter_deterministic" | "reporter_ai_review"
                             | "human"
promoted_at
confidence_basis         -- what evidence volume/quality backs this
superseded_by            -- if a later finding revises/retracts this one
```

No entry without `source_evaluation_record_id` may be promoted past
"Daily Observation" — this is the concrete mechanism enforcing prohibition
principle 1 in `docs/en/12_roadmap.md` (no memory-learning activation
before the evaluation foundation is trustworthy).

### 6.2 Source classification

```
SourceClass
  CANONICAL_EVALUATION   -- traced to a UEF record (highest trust)
  LEGACY_EVALUATION       -- traced to a pre-UEF legacy report only
                             (lower trust, must be labeled as such)
  OPERATOR_OBSERVATION    -- a human-entered note, not derived from data
  DERIVED_AGGREGATE       -- rolled up from multiple lower entries
```

A `LEGACY_EVALUATION`-sourced memory entry must be visibly labeled as
such in the Knowledge UI (Q100-4/Layer 4) and re-evaluated once UEF-4's
adapter for that program exists, so trust levels are never silently
conflated.

Status: **CONCEPT STAGE.** No vault, no promotion pipeline exists.

## 7. Q100-5 — Retrieval Layer

Extends Strategist's retrieval model (Architecture V2 §4.11) with an
explicit priority order for what gets retrieved into a context pack, most
to least prioritized:

```
1. CANONICAL_EVALUATION-sourced Lessons for the exact symbol + regime match
2. CANONICAL_EVALUATION-sourced Lessons for a related symbol/sector (per
   ProgramEntry.related_programs and known sector linkage)
3. Strategy Knowledge (fully promoted, stable) regardless of symbol, for
   the matching market regime
4. LEGACY_EVALUATION-sourced entries, explicitly labeled lower-trust
5. Recent Findings not yet promoted to Lesson (shown as provisional)
```

`DERIVED_AGGREGATE` and `OPERATOR_OBSERVATION` entries are retrievable but
never outrank a matching `CANONICAL_EVALUATION` Lesson at the same
specificity level.

Status: **DESIGN ONLY.**

## 8. Q100-6 — Self-Improvement Loop

```
Observe -> Decide -> Execute -> Evaluate -> Remember -> Retrieve -> Decide Better
```

(Same loop Architecture V2 §4.5 already defines; Q100-6 is that loop
operating at the research-program scale across many hypotheses rather
than one Strategist decision.)

### 8.1 Maturity ladder (7 levels)

```
Level 1  Manual review only        -- human reads reports, decides
Level 2  Structured reporting      -- Reporter produces structured
                                       attribution (Q100-3), human decides
Level 3  Advisory retrieval        -- Strategist/human can query memory
                                       (Q100-5), decision still human/
                                       Strategist-authored, memory never
                                       auto-applied
Level 4  Guided suggestion         -- system surfaces a specific
                                       promotion/demotion suggestion for a
                                       program's ResearchStatus, human
                                       approves/rejects
Level 5  Bounded auto-flagging     -- system can auto-flag (not
                                       auto-execute) a program as
                                       DEPRECATE_REVIEW or promote a
                                       Finding to Lesson under strict,
                                       auditable rules; no execution or
                                       strategy-parameter change results
Level 6  Autonomous parameter tuning  -- system adjusts strategy
                                          parameters directly (OUT OF SCOPE)
Level 7  Autonomous strategy authoring -- system creates/retires whole
                                           strategies (OUT OF SCOPE)
```

**Current target: Level 4-5 only.** Level 6-7 are explicitly out of scope
for every track in `docs/en/12_roadmap.md` (prohibition principle 7) and
are recorded here only to make the ladder's full shape and the current
ceiling explicit — not as a future commitment.

Status: **DESIGN ONLY.** No level above 1 (today's actual manual-review
reality) is implemented.

## 9. Reference Obsidian vault layout (example only, not implemented)

Reuses Architecture V2 §4.7's layout; repeated here with Q100-specific
annotations for clarity:

```
knowledge/
├─ Programs/            -- one note per Q100-1 ProgramEntry (Q10.md, ...)
├─ Markets/
├─ Strategies/
├─ Symbols/
├─ Experiments/
├─ Incidents/
├─ Decisions/
├─ Findings/            -- pre-Lesson, provisional (retrieval priority 5)
├─ Lessons/              -- promoted, CANONICAL_EVALUATION-sourced preferred
└─ Reports/
   ├─ Daily/
   ├─ Weekly/
   └─ Monthly/
```

This is an illustrative example of what the vault *would* look like if
built — it is not instantiated, and this document does not create it.

## 10. Non-goals

- No parallel metric-calculation engine (Q100 reads UEF, never
  recomputes).
- No autonomous production strategy modification (Level 6-7 out of
  scope).
- No Obsidian-as-database dependency (Q100-4 §6, same constraint as
  Architecture V2 §4.6/§4.7).
- No change to any existing Q9-Q18/Opening Alpha/Alpha Board calculation,
  threshold, or report.

## 11. Implementation status and start condition

```
IMPLEMENTATION STATUS: DEFERRED
```

Q100-1's registry *schema* and Q100-4's memory-provenance *schema* may be
drafted in parallel with Track A/B work (priority tier P4 in
`docs/en/12_roadmap.md`). Q100 execution against real canonical metrics
waits on UEF-3/UEF-4. Q100-6 Level 4-5 activation waits on Q100-4's
promotion pipeline existing and on UEF-9's freeze for whichever metrics
that pipeline depends on.
