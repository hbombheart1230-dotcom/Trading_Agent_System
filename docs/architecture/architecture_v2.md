# Trading Agent System — Architecture V2 (Design)

Status: **DESIGN ONLY — NOT IMPLEMENTED**
Scope: documentation and design proposal. No runtime, agent-prompt, strategy, or
execution code changes accompany this document.

This document follows the required reading order:

```
CURRENT IMPLEMENTATION
  -> CURRENT ROLE RESPONSIBILITIES
  -> LIMITATIONS
  -> ARCHITECTURE V2
```

It does not discard the existing system. It is a reclassification and
extension proposal layered on top of what already exists and what Step5C
already froze.

---

## 1. Current Implementation (as-is, verified against source)

Primary references read for this document: [README.md](../../README.md),
[docs/en/00_index.md](../en/00_index.md) through
[docs/en/13_project_tree.md](../en/13_project_tree.md),
[docs/en/99_glossary.md](../en/99_glossary.md), and
[docs/architecture/architecture.md](architecture.md), cross-checked against
the actual `libs/` and `graphs/nodes/` layout.

### 1.1 The 7-role model today

```
Commander -> Strategist -> Scanner -> Monitor -> Supervisor -> Executor -> Broker -> Reporter
```

Canonical entry points (verified in source, not just docs):

| Role | Canonical implementation | Compatibility/legacy shim |
|---|---|---|
| Commander | `graphs/commander_runtime.py` | `graphs/nodes/commander_node.py` (thin wrapper), `libs/agent/commander.py` (legacy scaffolding) |
| Strategist | `graphs/nodes/strategist_node.py` | `libs/agent/strategist.py` (legacy `Plan` adapter) |
| Scanner | `graphs/nodes/scanner_node.py` | `graphs/nodes/scan_candidates.py` (compatibility stage wiring) |
| Monitor | `graphs/nodes/monitor_node.py` | `libs/agent/monitor.py` (legacy placeholder) |
| Supervisor | `libs/risk/supervisor.py::Supervisor.allow()` | — |
| Executor | `graphs/nodes/execute_from_packet.py`, `libs/execution/executors/*` | `graphs/nodes/execute_order.py`, `graphs/nodes/executor_node.py` |
| Reporter | `libs/reporting/*`, `scripts/run_*report*.py` | — |

Execution-safety authority underneath Executor (frozen as of the Step5C
closure this document sits directly on top of):
`libs/supervisor/intent_state_store.py::SQLiteIntentStateStore`,
`libs/execution/intent_identity.py`,
`libs/execution/intent_admission.py`,
`libs/execution/intent_execution_owner.py`.

### 1.2 Strategy layer

`libs/strategies/` holds the strategy contracts and concrete strategies
(`regime_momentum_v1.py`, `mean_reversion_v1.py`, `news_momentum_v1.py`,
`universe_builder.py`, `contracts.py`, `playbook_contracts.py`). The
informally-named Q-series (Q9/Q10/Q12/Q13/Q14) and Opening Alpha live as
daily-patch/evaluation history under `docs/daily_patch/` and
`docs/evaluation/` (e.g. `docs/daily_patch/2026-09-07_q10_vwap_and_opening_alpha_integrity.md`,
`docs/evaluation/q12_vnext_delivery_time_alignment.md`) rather than as a
single canonical module — they are hypotheses and evidence trails
accumulated over many daily patches, not (yet) a formal experiment schema.

### 1.3 Existing lightweight memory

A narrow advisory memory already exists and is explicitly documented as
**advisory-only, non-authoritative**:

- `data/strategy_memory/feedback.jsonl` — append-only Reporter feedback
- `data/strategy_memory/daily/YYYY-MM-DD.json` — deduped daily summaries
- consumed by Strategist via `state["recent_strategy_feedback"]`
- explicitly: "advisory only; no automatic live parameter mutation"

This is the direct ancestor of the Experience/Memory Layer proposed below
— V2 does not invent memory from nothing, it formalizes and extends
something that already exists in a minimal form.

### 1.4 Observability already in place

`data/logs/events.jsonl` (EventLog), `state["decision_trace_ledger"]`
(alias `state["reason_ledger"]`), and the Evidence Ledger
(`data/evidence_ledger/events.jsonl`) already capture per-run reasoning
snapshots per agent, decision links, and raw LLM prompt/response pairs.
Reporter already runs a two-layer model (deterministic baseline +
optional passive AI review) and already writes
`strategist_evaluation` / `scanner_evaluation` / `monitor_evaluation` /
`supervisor_activity` / `incidents` / `improvement_suggestions` sections.

### 1.5 Execution-safety layer (Step5B → Step5C, frozen)

- **Step5B**: broker-mutation at-most-once semantics — `BrokerOutcome`
  4-state classification, UNKNOWN quarantine, physical HTTP
  at-most-once, token-invalid-no-replay.
- **Step5C** (frozen — see [step5c_execution_owner.md](../development/step5c_execution_owner.md)):
  canonical intent-ownership store, atomic CAS claim, physical-order
  duplicate guard, explicit admission authority, mutation-symbol
  fail-closed handling, consumer-only `claim_execution()`.
- **Step5D / Step5E / Step6**: not yet started. Step5D owns broker-truth
  reconciliation; Step5E owns safe operator recovery; Step6 is the
  integrated execution-safety freeze. Architecture V2 sits strictly
  above this stack and does not touch it.

---

## 2. Current Role Responsibilities (as documented and as implemented)

| Role | Responsibility today |
|---|---|
| Commander | Orchestrates the run cycle, decides which agent runs next, routes state between agents, handles abnormal events (guard block, LLM failure, emergency stop). Never selects stocks, never executes. |
| Strategist | AI-centered strategic framing: market regime/sentiment, themes, playbook, scanner/monitor/reporter guidance, optional candidate hints. Optionally calls an LLM. Reads advisory `recent_strategy_feedback`. |
| Scanner | Builds/filters/ranks the candidate universe from Kiwoom data, applies Strategist's frame additively, hydrates features/quotes, selects Top-1. No LLM reasoning in the canonical path. |
| Monitor | Watches the selected symbol/position, emits `OrderIntent` (BUY/SELL/NOOP) only. Structurally forbidden from executing. Deterministic hold/exit-confirmation policy. |
| Supervisor | Owns risk limits/policy, validates `OrderIntent`, documented as returning approve/reject/**modify**, can pause/stop the system. |
| Executor | Executes approved intents only, applies guard precedence, ensures idempotency, routes to the broker. |
| Reporter | Reads EventLog, produces deterministic + optional AI-reviewed reports, persists advisory strategy-memory feedback, does not participate in runtime decision routing. |

---

## 3. Limitations (why V2 is being proposed)

These are documentation/design observations only — none require or imply
a code change in this pass:

1. **"7 Agents" as a label overstates uniformity.** Scanner and Monitor
   are close to deterministic engines already; Strategist and Reporter's
   AI-review layer are the only steps that meaningfully need strong
   reasoning. Calling all seven "agents" obscures that split and invites
   scope creep toward making everything an LLM call.
2. **Memory is currently a single narrow channel.** `recent_strategy_feedback`
   is useful but flat — it has no schema linking a decision to its
   outcome, no promotion/demotion of "noise" vs. "lesson," and no
   retrieval scoped to today's specific market context.
3. **Q-series hypotheses live in prose, not in a queryable evidence
   structure.** Daily patches document individual observations well, but
   there is no canonical `ExperienceRecord`/`StrategyEvidence` schema
   tying a hypothesis to its accumulated daily evidence over time.
4. **Reporter's evaluation is post-run and comprehensive, but not yet a
   feedback loop with retrieval.** Reporter writes evaluations; nothing
   currently curates or promotes them into something Strategist actively
   retrieves by context.
5. **No formal boundary yet between "operational truth" and "knowledge
   memory."** The canonical SQLite intent-state authority
   (Step5C) and the advisory JSONL strategy memory happen to already be
   separate files today, but there is no written invariant guaranteeing
   they stay separate as the system grows a real memory layer.
6. **Supervisor's documented "modify" capability is not implemented.**
   `libs/risk/supervisor.py::Supervisor.allow()` returns an
   allow/reason/details triple; there is no modify branch in code. (This
   mismatch is called out explicitly, not resolved, in this document —
   see §12.)
7. **No standing principle yet stating "more agents ≠ better system."**
   Without that written down, the natural next step for any of these
   limitations is "add another LLM-calling agent," which V2 explicitly
   argues against.

---

## 4. Architecture V2

### 4.1 Core hypothesis

> System quality does not improve by adding more agents. It improves by
> clearly separating where strong reasoning is required from where
> deterministic execution is required — concentrating model intelligence
> in Strategist and Reporter/Evaluator, and strengthening everything else
> as orchestration, data, timing, policy, and execution harness.

The 7 roles are **kept**. What changes is the label: not "7 Agents" but
**7 Specialized Roles**, each explicitly classified by how much of its
job is reasoning versus deterministic harness work.

### 4.2 Role reclassification

| Role | Current label | V2 label | Reasoning level | Determinism requirement | Primary inputs | Primary outputs | Memory interaction | Execution authority |
|---|---|---|---|---|---|---|---|---|
| Commander | Commander Agent | **Orchestration Harness** | Minimal (routing logic only) | High | run config, state, agent outputs, failure signals | next-node routing, retry/stop decisions | none (routes context, doesn't curate it) | none |
| Strategist | Strategist Agent | **Market Reasoning Agent** | High (primary reasoning role) | Low (deliberately) | market/news/macro data, retrieved Experience Memory context pack | market regime, scenario, priority, confidence, scanner/monitor guidance | reads via retrieval (context pack); does not write directly | none |
| Scanner | Scanner Agent | **Data / Feature / Ranking Engine** | Minimal-to-none | High | Strategist guidance, Kiwoom market data | ranked candidates, Top-1, score breakdown | none | none |
| Monitor | Monitor Agent | **Microstructure / Timing State Engine** | Minimal-to-none (rule/state-machine first) | High | position state, tick/quote data, Strategist guidance | `OrderIntent` (BUY/SELL/NOOP) | none | none (structurally forbidden) |
| Supervisor | Supervisor Agent | **Policy / Authority / Risk Engine** | Minimal-to-none | Very high (reproducibility/auditability first) | `OrderIntent`, risk limits, Step5C intent/admission state | approve/reject decision (modify: see §12) | none | gate only, no execution |
| Executor | Executor Agent | **Execution Service / Execution Harness** | None | Very high | approved+admitted intent | broker mutation, execution result | none | yes — sole execution authority, under Step5B/5C contracts |
| Reporter | Reporter Agent | **Evaluator + Memory Curator** | High (evaluation reasoning) | Low-to-medium | EventLog, Decision Trace, Evidence Ledger, outcomes | evaluations, findings, promoted memory candidates | writes (curates promotions into Experience Memory) | none |

Note the explicit caveat carried from the user's own spec: some V2 roles
may still use a limited LLM call in real implementation (e.g. Reporter's
existing optional AI-review layer). The classification is about where
**final decision responsibility and execution determinism** sit, not a
literal ban on any LLM token anywhere in a role's implementation.

### 4.3 Reasoning agents vs. deterministic harness

```
Strong Reasoning Layer
├─ Strategist               (Market Reasoning Agent)
└─ Reporter / Evaluator     (Evaluator + Memory Curator)

Deterministic Harness Layer
├─ Commander                (Orchestration Harness)
├─ Scanner                  (Data/Ranking Engine)
├─ Monitor                  (Timing State Engine)
├─ Supervisor               (Policy/Authority/Risk Engine)
└─ Executor                 (Execution Service)
```

The point of this split is **not** "Agent vs. not-Agent" as a literal
implementation detail — it is separating final decision responsibility
(reasoning layer) from execution determinism (harness layer), so that
future work knows which layer a given improvement belongs to.

### 4.4 Architecture V2 diagram

```
                   Commander
             Orchestration Harness
                       |
                       v
                  Strategist
                Reasoning Agent  <───────────────┐
                       |                          │
                       v                          │ retrieval
                    Scanner                       │
               Data/Ranking Engine                │
                       |                          │
                       v                          │
                    Monitor                       │
                Timing State Engine                │
                       |                          │
                       v                          │
                  Supervisor                       │
             Policy/Authority Engine               │
                       |                          │
                       v                          │
                   Executor                        │
              Execution Service                    │
                       |                          │
                       v                          │
                    Broker                          │
                       |                          │
                       v                          │
                   Reporter                        │
             Evaluator/Memory Curator              │
                       |                          │
                       v                          │
              Experience Memory  ──────────────────┘
```

Two layers sit beside (not inside) this chain and are kept explicitly
separate (see §4.6):

```
Operational Truth              Knowledge Memory
SQLite / EventLog              Experience Vault
(Step5C canonical              (Markdown-based,
 intent/admission/              Reporter-curated,
 execution state)               Strategist-retrieved)
```

### 4.5 The Experience / Memory Layer

This is **not an 8th agent or role**. It is a layer the reasoning roles
read from and write to.

```
Observe -> Decide -> Execute -> Evaluate -> Remember -> Retrieve -> Decide Better
```

Full loop:

```
Market Context
     |
     v
Strategist
     |
     v
Decision
     |
     v
Scanner / Monitor
     |
     v
Execution
     |
     v
Outcome
     |
     v
Reporter / Evaluator
     |
     v
Experience Memory
     |
     └─────────────────────────► Strategist retrieval (next cycle)
```

### 4.6 Operational Truth vs. Knowledge Memory — a hard boundary

This is the single most important invariant this document introduces:

```
SQLite / EventLog / canonical execution state  =  Operational Truth
Knowledge Vault / Experience Memory            =  Analytical / Historical Knowledge
```

- Knowledge memory **must never** become broker execution authority.
- If the Knowledge Vault is stale, corrupt, or unavailable, the
  execution-safety contract (Step5B/Step5C, and later Step5D/5E/6) must
  keep working exactly as if memory did not exist.
- Concretely: `SQLiteIntentStateStore`, `intent_admission`,
  `physical_order_claim` (Step5C) remain the only sources of execution
  truth. A Markdown vault entry, however confident-sounding, is never a
  valid input to `claim_execution()`, `admit_order_intent()`, or any
  broker-mutation guard.
- Today's `data/strategy_memory/*` is already correctly on the
  "advisory, non-authoritative" side of this line — V2 formalizes that
  as a named boundary rather than an implicit convention.

### 4.7 Reference Experience Vault layout (Markdown, portable)

Obsidian is treated as a *UI/exploration tool over* the vault, never as
a runtime dependency. The vault itself is plain Markdown so it stays
portable if a different viewer is used later.

```
knowledge/
├─ Markets/
│  └─ YYYY-MM-DD.md
│
├─ Strategies/
│  ├─ Q10.md
│  ├─ Q12.md
│  └─ OpeningAlpha.md
│
├─ Symbols/
│  ├─ SamsungElectronics.md
│  ├─ SKHynix.md
│  └─ WooriTechnologyInvestment.md
│
├─ Experiments/
├─ Incidents/
├─ Decisions/
├─ Findings/
├─ Lessons/
│
└─ Reports/
   ├─ Daily/
   ├─ Weekly/
   └─ Monthly/
```

Example cross-links inside a note: `[[Q10]]`, `[[SK Hynix]]`, `[[SOX]]`,
`[[OVERREACTION]]`, `[[DIVERGENCE]]`, `[[Opening Alpha]]`,
`[[Incident-2026-09-01]]`.

`Obsidian = UI / exploration tool` and `Markdown Vault = portable storage
representation` is the preferred direction to evaluate first, rather
than adopting Obsidian-specific features the system itself depends on.

### 4.8 Experience record schema (conceptual — not implemented)

```
ExperienceRecord
  id
  timestamp
  market_context
  strategy
  symbol
  scenario
  decision
  confidence
  entry_context
  exit_context
  outcome
  mfe
  mae
  pnl
  failure_class
  lesson
  related_experiment
  related_incident
  evidence
  source_run_id
```

Related conceptual schemas:

```
DecisionRecord     -- what was decided, with what confidence, why
ExperimentRecord   -- a Q-series-style hypothesis and its accumulated evidence
IncidentRecord      -- what went wrong operationally (distinct from a bad but "clean" trade)
StrategyEvidence    -- the aggregated evidence trail feeding a strategy's lesson set
```

`ExperienceRecord` is the atomic unit; `DecisionRecord`/`ExperimentRecord`/
`IncidentRecord` group records by lens; `StrategyEvidence` is the rolled-up
view a Strategist retrieval query actually wants to read.

### 4.9 Memory promotion hierarchy

Not every daily observation becomes long-term memory. A promotion
hierarchy prevents memory pollution, duplicate lessons, and temporary
noise from ever reaching Strategist retrieval:

```
Raw Event
   |
   v
Daily Observation
   |
   v
Repeated Evidence
   |
   v
Finding
   |
   v
Lesson
   |
   v
Strategy Knowledge
```

Promotion criteria (conceptual, for future design, not thresholds to
implement now): a Raw Event becomes a Daily Observation once Reporter's
existing deterministic analysis flags it; a Daily Observation becomes
Repeated Evidence only once the same pattern recurs across multiple
independent runs/days; Repeated Evidence becomes a Finding once Reporter
(or a human) can state the pattern and its apparent cause; a Finding
becomes a Lesson once it has survived at least one out-of-sample check;
a Lesson becomes Strategy Knowledge once it is stable enough to be
retrieved by Strategist as established context rather than a fresh
hypothesis.

### 4.10 Reporter V2 lifecycle

Reporter becomes **Evaluator + Memory Curator**, operating on three
cadences layered on top of its current daily/weekly/monthly reports:

**Daily**
- What did we judge today?
- What executed?
- What was right?
- What was wrong?
- What should tomorrow remember?

**Weekly**
- Recurring success/failure patterns
- Per-strategy evidence accumulation
- Strategist scenario performance
- Scanner ranking quality
- Monitor timing quality
- Execution quality

**Monthly**
- Strategy keep/adjust/deprecate candidates
- Regime-level performance
- Long-term patterns
- Experiment outcomes
- System-level lessons

### 4.11 Strategist retrieval model

Strategist does not receive the entire memory store. It receives a
context pack scoped to today's actual market context:

```
Memory Retrieval -> Context Pack -> Strategist reasoning
```

Example: if today's context is "SOX strong, Hynix gap up, USD/KRW weak,"
retrieval should prioritize: SOX → Hynix historical cases, gap-up
continuation/reversal cases, similar FX regimes, prior Q10 outcomes, and
related incidents — not an unfiltered dump of all prior memory.

### 4.12 Harness Engineering Principles

A dedicated section, because V2's core hypothesis is that harness quality
matters more than agent count:

```
context selection
context compression
tool selection
state persistence
memory retrieval
evaluation
observability
replayability
failure isolation
deterministic execution boundaries
```

Core philosophy:

```
More Agents
≠
A Better System

Better Harness
+ Better Context
+ Better Evaluation
= A Better Agent System
```

### 4.13 LLM call structure — review candidates (not changed now)

Existing LLM call points to revisit in a future phase (deferred, not
touched here):

- Strategist premarket reasoning
- Scanner result interpretation (where it exists today)
- hold decision
- overnight decision
- Reporter evaluation

Questions to ask of each, later:

- Does this judgment genuinely need an LLM?
- Would a deterministic rule suffice?
- Can this be folded into a single Strategist context-aware decision?
- Can this move to Reporter's post-run evaluation instead of being made
  live?

No call-structure changes are made in this pass.

### 4.14 Evaluation-first architecture

Before adding a feature, V2 requires answering: **"How will we know it
helped?"** Every major judgment should be able to carry:

```
input
decision
confidence
expected outcome
actual outcome
evaluation
```

so that, over time, these become independently measurable:

- Strategist effectiveness
- Scanner rank quality
- Monitor timing quality
- execution quality
- memory usefulness

### 4.15 Q-series integration

Q9/Q10/Q12/Q13/Q14 and Opening Alpha are **not removed or replaced**.
They connect into the Experiment/Strategy Evidence layer:

```
Q10
  -> hypothesis
  -> daily observations
  -> accumulated evidence
  -> strategy lesson
```

The existing daily-patch and evaluation documents
(`docs/daily_patch/*q10*`, `docs/evaluation/q12_*`, etc.) are the raw
material this schema would eventually organize — V2 gives them a home,
it does not obsolete them.

### 4.16 Relationship to Step5B–Step6

Architecture V2 sits **on top of**, and never replaces, the
execution-safety stack:

```
Step5B   Physical broker mutation safety
Step5C   Execution authority / ownership          (frozen)
Step5D   Broker truth reconciliation                (not started)
Step5E   Safe operator recovery                     (not started)
Step6    Integrated execution-safety freeze         (not started)
```

Only above that stack does Architecture V2 begin:

```
Architecture V2
  Harness
  Context
  Memory
  Evaluation
  Reasoning optimization
```

### 4.17 Implementation status and start condition

```
IMPLEMENTATION STATUS: DEFERRED
```

Start condition: **Step6 `REFACTORING COMPLETE`.** No part of Architecture
V2 — role reclassification aside, since that is a documentation-only
relabeling — is implemented before that gate.

```
Current
  -> Step5D
  -> Step5E
  -> Step6
  -> REFACTORING COMPLETE
  -> Architecture V2 Phase 1
```

### 4.18 Architecture V2 phases (roadmap only, not implemented)

- **Phase V2-1 — Role Reclassification**: formalize the 7-role
  redefinition, document responsibility cleanup, write down the LLM vs.
  deterministic boundary per role.
- **Phase V2-2 — Experience Schema**: design the canonical
  `ExperienceRecord`/`DecisionRecord`/`ExperimentRecord`/`IncidentRecord`/
  `StrategyEvidence` schemas.
- **Phase V2-3 — Reporter → Evaluator**: build daily evaluation, weekly
  aggregation, monthly evidence, and memory-candidate generation.
- **Phase V2-4 — Knowledge Vault**: stand up the Markdown/Obsidian-
  compatible vault with linking, metadata, and provenance.
- **Phase V2-5 — Strategist Retrieval**: relevant-experience retrieval,
  context-pack construction, memory-usefulness evaluation.
- **Phase V2-6 — LLM Call Simplification**: re-evaluate each existing LLM
  call site's necessity; convert what can be deterministic.
- **Phase V2-7 — Evaluation Loop**: decision quality, retrieval quality,
  memory usefulness, strategy improvement — measured, not assumed.

---

## 5. What Architecture V2 explicitly does not do

- Does not treat "more agents" as a goal in itself.
- Does not turn every role into an LLM agent.
- Does not use Obsidian as an operational database.
- Does not let memory participate in execution authority.
- Does not let Reporter auto-modify strategy.
- Does not let an LLM directly decide broker execution.
- Does not store raw, unfiltered reports in memory without limit.
- Does not mix the execution-safety layer with the reasoning layer.

---

## 6. The Supervisor "modify" contract gap (documented, not resolved)

`docs/en/01_overview.md`, `02_principles.md`, and
`docs/alignment/03_agent_roles_inputs_outputs_and_handoffs.md` describe
Supervisor as returning `approve/reject/modify`. The actual
implementation, `libs/risk/supervisor.py::Supervisor.allow()`, returns
`AllowResult(allow: bool, reason: str, details: dict)` — there is no
`modify` branch in code (`grep -i "modify" libs/risk/` matches only a
docstring, no logic). Architecture V2 does not implement `modify` and
does not resolve this mismatch; it is recorded here as a pre-existing
gap for a future, separately-scoped decision, consistent with how it was
first flagged.

---

## 7. Summary comparison

| Aspect | Current (as documented) | Architecture V2 |
|---|---|---|
| Role count | "7 Agents" | 7 Specialized Roles (same 7, reclassified) |
| Reasoning concentration | Implicit, spread unevenly | Explicit: Strategist + Reporter/Evaluator only |
| Memory | One advisory JSONL channel | Layered Experience Memory with promotion hierarchy and retrieval |
| Memory vs. execution | Not written down as an invariant (but already correctly separated in practice) | Explicit hard boundary: Operational Truth vs. Knowledge Memory |
| Q-series | Documented as prose/evaluation history | Connected to a conceptual Experiment/Evidence schema |
| Reporter | Deterministic + optional AI review | Evaluator + Memory Curator, with daily/weekly/monthly promotion |
| Supervisor "modify" | Documented but not implemented | Left as-is, gap explicitly recorded |
| Implementation timing | N/A | Deferred until Step6 `REFACTORING COMPLETE` |

---

## 8. Six-layer system model (2026-09-13 update, design only)

This section reconfirms and extends §4.4–§4.6 above into a full six-layer
model, now that the Unified Evaluation Foundation (UEF) work and the Q100
Alpha Research & Learning Program have been separately planned (see
[`docs/en/12_roadmap.md`](../en/12_roadmap.md) `## Post-Step6 and parallel
tracks` and
[`docs/research/q100_research_and_learning_roadmap.md`](../research/q100_research_and_learning_roadmap.md)).
It does not replace §4.4–§4.6; it names the same boundary at system scope
rather than only around Strategist/Reporter.

```
Layer 1  Operational Truth        data/, SQLite, EventLog, chronicles
                                   (Step5B/5C/5D/5E/Step6 authority — never
                                    migrated into the Knowledge Vault)
Layer 2  Evaluation Truth         UEF canonical records (EpisodeRecord/
                                   PairRecord/SequenceRecord/AggregateRecord)
                                   + the reports built from them
Layer 3  Knowledge                docs/ (normative + research) and
                                   validated memory (promoted
                                   ExperienceRecord/Lesson entries)
Layer 4  Knowledge UI             Obsidian vault — a view over Layer 3,
                                   never itself an authority
Layer 5  Reasoning / Learning     Strategist (Market Reasoning Agent),
                                   Reporter/Evaluator (Evaluator + Memory
                                   Curator), Q100 (research/learning
                                   authority over Layer 2/3)
Layer 6  Execution                Supervisor, Executor, Broker
```

Ordering rule: Layer *n* may read from any layer below it, but a lower
layer never depends on a higher one for correctness. Layer 6 (Execution)
in particular has zero read dependency on Layers 3/4/5 — this is the same
invariant §4.6 already states for Operational Truth vs. Knowledge Memory,
restated here so it is visible at the six-layer scale rather than only
between two named layers.

### 8.1 Memory is not the 8th agent

Restating §4.5 explicitly at system scope: the Experience/Memory Layer
(Layers 3–4 above) is **not a role and not an agent**. It is shared state
that exactly two reasoning roles interact with — Strategist reads it
(via retrieval, §4.11), Reporter/Evaluator writes to it (via curation,
§4.10) — and that Q100 also reads from and writes to under its own
namespace (Q100-4/Q100-5, see the Q100 roadmap doc). The 7-role model
(§4.2) is unchanged: still 7 roles, still reclassified as reasoning vs.
harness, never 8.

### 8.2 Docs / Reports / Memory — role definitions

Three artifacts easily get confused because they can all describe the
same event. They answer three different questions and live in three
different places:

| Artifact | Answers | Lives in | Authority |
|---|---|---|---|
| **Docs** | "Why was this designed this way?" | `docs/` — split into *Normative* (architecture, contract, policy — e.g. this file, `docs/io_contracts.md`, `docs/ground_rules/`) and *Research* (hypothesis, experiment, review — e.g. `docs/research/`, `docs/daily_patch/`) | Normative docs describe binding contracts; research docs describe findings and are never binding on their own |
| **Reports** | "What happened?" | `reports/`, Reporter output, UEF Layer-2 evaluation records | Authoritative for what occurred, within that report's own stated scope/window |
| **Memory** | "What did we learn?" | Layer 3 (Knowledge) — promoted `ExperienceRecord`/`Lesson` entries, surfaced through the Layer 4 Obsidian UI | Advisory only (per §4.6); never execution authority; a Lesson's confidence is only as good as the Evaluation Truth (Layer 2) it was promoted from |

A Lesson is never written directly from a raw event — it must trace
through a Report (Layer 2 evaluation) first, per the promotion hierarchy
already defined in §4.9. This is the concrete meaning of prohibition
principle 1 in the roadmap doc: no memory-learning activation before
the evaluation foundation (UEF-3) exists to make that trace trustworthy.

### 8.3 Full flow diagram

```
data/ (Operational Truth)
     |
     v
UEF canonical records (Evaluation Truth)
     |
     v
reports/ (Reporter / Evaluator output)
     |
     v
Reporter/Evaluator curation  ───────────────► docs/ (Research: findings,
     |                                          reviews — human-written,
     |                                          not auto-generated)
     v
Memory promotion (Layer 3: ExperienceRecord -> Lesson)
     |
     v
Knowledge Vault (Markdown, portable)
     |
     v
Obsidian Knowledge UI (Layer 4 — view only)
     |
     ├────────────────────────────► Strategist retrieval (next cycle, §4.11)
     └────────────────────────────► Q100 research/learning retrieval
                                     (Q100-5, reads Layers 2-3 under its
                                      own namespace, never Layer 1)
```

### 8.4 Merge note

This section is additive to, and must be read together with, §4.4
(Architecture V2 diagram) and §4.6 (the Operational-Truth-vs-Knowledge-
Memory hard boundary) — it does not redefine either. Where terminology
here (`Evaluation Truth`, `Knowledge`, `Knowledge UI`) and §4's terms
(`Operational Truth`, `Knowledge Memory`, vault) appear to overlap:
`Evaluation Truth` = UEF's Layer-2 canonical records specifically (a
concept that did not exist when §4 was first written); `Knowledge` and
`Knowledge Memory` refer to the same thing; `Knowledge UI` and `Obsidian`
refer to the same thing. No conflict is introduced; this section only
adds the UEF/Q100 vocabulary that postdates the original §4 draft.

Implementation status: **DEFERRED**, same start condition as §4.17
(Step6 `REFACTORING COMPLETE`), plus UEF-9's formal freeze for any part
of Layer 2 this model depends on (see the dependency graph in
`docs/en/12_roadmap.md`).
