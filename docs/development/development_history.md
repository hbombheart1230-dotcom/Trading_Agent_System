# Trading Agent System Development History

## Purpose

This document reconstructs the repository history up to the pre-Claude
architecture-refactoring baseline. It is an evidence index, not a claim that
every historical design document was implemented exactly as written.

Baseline boundary:

- date: `2026-08-31`
- commit: `6aa4e398e2e1c33482cab3dbf2518e7b03c18a10`
- status: current Human + Codex-era AS-IS before Claude Code refactoring

## Confidence Scale

- `VERIFIED`: directly supported by Git diff/history and matching code, tests,
  or contemporaneous documentation.
- `SUPPORTED`: supported by multiple repository signals, but one part such as
  exact date, implementation extent, or agent identity is not independently
  proven.
- `UNCERTAIN`: only partial or retrospective evidence exists.
- `UNKNOWN`: the current repository cannot establish the claim.

Agent attribution is deliberately separate from milestone verification. A
milestone can be `VERIFIED` while its implementing AI agent remains `UNKNOWN`.

## Attribution Baseline

Unless stronger evidence is attached to an individual milestone, use:

```text
Architecture Direction : Human
Technical Design        : Human + AI Agent
Implementation          : AI Agent or Unknown
Verification            : AI Agent + Automated Tests
Final Approval           : Human
```

This is a governance model, not proof of historical authorship. Git author
metadata uses one human account for all 374 baseline commits and cannot
separate Human, Codex, Gemini, or another tool.

## Timeline

### 1. Pre-Git Foundation, M1-M13

**Date / period:** repository records describe `2026-02-07` through
`2026-02-11`; the first Git commit is later.

**Purpose:** establish the Kiwoom catalog/request stack, read layer, dry-run
execution boundary, Scanner, Strategist provider hook, and repeated runtime.

**Major changes:** archived plans describe API discovery/planning, HTTP/token
clients, account/price readers, decision packets, mock/real executors, Scanner,
Strategist, and M13 runtime-loop work.

**Affected components:** `docs/plan/archive`, `libs/catalog`, `libs/kiwoom`,
`libs/read`, `libs/execution`, `graphs/pipelines`.

**Architecture impact:** this is the inferred foundation inherited by the first
repository snapshot, not a commit-by-commit history available in this Git
repository.

**Primary agent / human role:** `UNKNOWN`; product direction is treated as
Human-owned under the project governance model, but historical execution
attribution is not recoverable.

**Verification:** corresponding code and tests exist in the first Git snapshot.

**Evidence:** archived M3-M14 plans and commit `46934dc`.

**Confidence:** functionality `SUPPORTED`; exact chronology and attribution
`UNCERTAIN`.

### 2. V6 Architecture Snapshot

**Date / period:** `2026-02-12`.

**Purpose:** commit a design-first Kiwoom agentic trading system as a coherent
repository baseline.

**Major changes:** 166 files and 8,249 inserted lines introduced the basic
Strategist -> Scanner -> Monitor -> Supervisor -> Execution flow, Kiwoom REST
integration, mock/real executors, DTO/IO contracts, EventLog, state handling,
reports, and tests.

**Affected components:** `graphs`, `libs`, `scripts`, `tests`, `docs`.

**Architecture impact:** agent separation, two-phase approval, mock/real
separation, and traceability were present from the first Git snapshot. They are
not later retrofits.

**Primary agent / human role:** implementation agent `UNKNOWN`; final repository
approval is Human-owned.

**Verification:** source and test tree in the commit.

**Evidence:** `46934dc`, original `README.md`, `docs/architecture`, and 48
initial test files.

**Confidence:** milestone `VERIFIED`; implementation attribution `UNKNOWN`.

### 3. M20 Enterprise and LLM Observability

**Date / period:** `2026-02-14` through `2026-02-15`.

**Purpose:** harden LLM integration and expose its operational cost and failure
state.

**Major changes:** legacy LLM router compatibility, smoke visibility,
Strategist metrics, prompt/schema telemetry, token/cost reporting, and LLM
circuit-breaker fallback.

**Affected components:** Strategist provider/router, EventLog, metrics, daily
reporting, roadmap documentation.

**Architecture impact:** LLM remained advisory and observable rather than
becoming execution authority.

**Primary agent / human role:** `UNKNOWN`; no agent-specific commit trailer.

**Verification:** targeted M20 tests and report/schema checks.

**Evidence:** `3a08fe0`, `e0ad92e`, `b842c68`, `57431c6`, `c4e0b6d`,
`ca4dd9b`, `7a5ed20`.

**Confidence:** `VERIFIED`.

### 4. M21-M22 Canonical Commander and Skill-Native Agents

**Date / period:** `2026-02-15` through `2026-02-16`.

**Purpose:** provide one canonical runtime entry and stable Scanner/Monitor
skill contracts.

**Major changes:** canonical Commander runtime, explicit mode/phase transitions,
decision-packet activation guard, graph-spine parity, legacy Commander bridge,
skill-native Scanner/Monitor, DTO standardization, hydration, and timeout
fallbacks.

**Affected components:** `graphs/commander_runtime.py`, Scanner, Monitor,
composite skills, DTO contracts, smoke checks.

**Architecture impact:** legacy paths became compatibility adapters around a
canonical orchestration boundary.

**Primary agent / human role:** `UNKNOWN`.

**Verification:** M21/M22 unit, parity, hydration, and closeout tests.

**Evidence:** `5fc215d` through `9bebafe`.

**Confidence:** `VERIFIED`.

### 5. M23-M25 Resilience, Intent State, and Operations

**Date / period:** `2026-02-17`.

**Purpose:** make failure, approval, duplicate execution, and operational alert
state deterministic.

**Major changes:** runtime resilience contract and circuit breaker, safe degrade
policy, SQLite intent state machine, CAS execution claims, JSONL/SQLite
reconciliation, execution preflight denial codes, metrics schema freeze,
alerts, scheduler hooks, notification retries, and ops queries.

**Affected components:** Commander, Strategist, Supervisor state store,
Executor preflight, metrics, notifications, runbooks.

**Architecture impact:** approval and execution became persistent, auditable,
and idempotency-aware.

**Primary agent / human role:** `UNKNOWN`.

**Verification:** M23-M25 closeout, state-machine, precedence, metrics, and alert
tests.

**Evidence:** `4fb321a`, `fcc94f1`, `c17ac2a`, `049b43f`, `26f3b8b`,
`588d4e5`, `8cb1e2e`, `c536d89`.

**Confidence:** `VERIFIED`.

### 6. M26-M30 Evaluation, Portfolio, Lifecycle, and Quality Gates

**Date / period:** `2026-02-20` through `2026-02-21`.

**Purpose:** extend the runtime from one strategy and ad-hoc checks to bounded
evaluation, portfolio control, operational profiles, and release governance.

**Major changes:** fixed-dataset replay/A-B scorecards, promotion gates,
multi-strategy allocation and conflict resolution, portfolio budgets, runtime
profiles/lifecycle hooks, deployment templates, feature/exit/sizing modules,
audit/log/disaster-recovery checks, and final release signoff gates.

**Affected components:** evaluation scripts, portfolio allocation, runtime
profiles, Monitor/Scanner, governance scripts, tests.

**Architecture impact:** added deterministic evaluation and operational control
around the trading core.

**Primary agent / human role:** `UNKNOWN`.

**Verification:** M26-M30 test and closeout suites.

**Evidence:** `660fea3`, `5702872`, `71c37a8`, `b106cd2`, `a757854`,
`ac8ae83`.

**Confidence:** `VERIFIED`.

### 7. M31 Mock-Operation and Post-Go-Live Hardening

**Date / period:** `2026-02-21` through `2026-03-08`.

**Purpose:** operate the integrated system repeatedly in Kiwoom mock mode with
readiness and safety evidence.

**Major changes:** mock-investor exam, SLO/incident workflow, scheduling,
OpenRouter hardening, max-hold/EOD liquidation, single-instance locks,
feature/regime engine, strategy registry, richer universe/data-quality/sizing,
operator summaries, and readiness gates.

**Affected components:** runtime entry scripts, Commander, Strategist, Scanner,
Monitor, strategy modules, scheduler, reports.

**Architecture impact:** converted milestone scaffolds into an operated mock
trading runtime.

**Primary agent / human role:** the M31 readiness audit explicitly identifies
Codex as auditor (`VERIFIED`). The surrounding implementation agent remains
`UNKNOWN` at commit level.

**Verification:** M31 readiness artifacts and targeted tests.

**Evidence:** `f20826a`, `8d3ea93`, `e8bba4c`, `690c315`, `6ba1414` and
`docs/plan/m31_operational_readiness_audit_2026-03-08.md`.

**Confidence:** milestone `VERIFIED`; broad Codex attribution `UNCERTAIN`.

### 8. Canonical Role Boundaries, Reporter, and Memory

**Date / period:** `2026-03-10` through `2026-03-13`.

**Purpose:** make all seven stages visible and separate policy proposal,
selection, intent, approval, execution, and post-run analysis.

**Major changes:** role-boundary alignment, integrated Strategist/Scanner/
Monitor contracts, full agent pipeline trace, passive Reporter AI review,
evidence ledger, canonical report layout, strategy-memory feedback, macro/news
context, and initial read-only operator UI.

**Affected components:** all agent nodes, Reporter, EventLog, UI, memory.

**Architecture impact:** established the current seven-role interpretation and
made Reporter/memory observational rather than execution-authoritative.

**Primary agent / human role:** `UNKNOWN`.

**Verification:** pipeline trace, Reporter, role-boundary, and UI tests.

**Evidence:** `a7def76`, `c97a8e8`, `7a2e68d`, `e03b132`, `5efe95e`,
`a17b828`, `efa45a6`.

**Confidence:** `VERIFIED`.

### 9. Canonical Event and Artifact Contracts

**Date / period:** `2026-03-18` onward.

**Purpose:** stop reconstructing every fact from a monolithic event stream and
persist per-agent decision evidence.

**Major changes:** canonical event schema, agent-output contracts, per-run
canonical artifacts, normalized LLM artifacts, artifact links, validation, and
trade lifecycle assembly.

**Affected components:** EventLog, canonical artifact writer, agent outputs,
trade reporting, UI readers.

**Architecture impact:** established the truth order later summarized as
canonical artifact -> trade artifact -> event fallback.

**Primary agent / human role:** `UNKNOWN`.

**Verification:** canonical artifact, schema, report-bundle, and UI tests.

**Evidence:** `f970488`, `4381491`, `docs/canonical_event_schema.md`,
`docs/canonical_artifact_flow.md`.

**Confidence:** `VERIFIED`.

### 10. Policy-Aware Ownership and Deterministic Reporting

**Date / period:** `2026-04-02` through `2026-04-30`.

**Purpose:** distinguish current AS-IS from target architecture and migrate
policy ownership without breaking legacy paths.

**Major changes:** unified runtime spec, current/target alignment documents,
Strategist proposal versus Commander applied-policy ownership, deterministic
read models, Kiwoom broker-truth readers, memory contracts, report ownership,
and additive compatibility migration.

**Affected components:** Commander, Strategist, Monitor, contracts, Kiwoom read
layer, Reporter, memory, documentation.

**Architecture impact:** moved from implicit environment/legacy behavior toward
policy-aware ownership and deterministic fact surfaces.

**Primary agent / human role:** from `2026-04-07`, repository workflow says
`Codex implements -> Gemini reviews -> Codex finalizes`. This supports a
Codex-centered workflow but does not prove each commit's implementer.

**Verification:** policy, reporting, truth-surface, and alignment tests.

**Evidence:** `d3d8078`, `f5f326a`, `3a37f1c`, `740e853`, `7d26984`,
`docs/alignment`, `docs/dev/workflow.md`.

**Confidence:** milestone `VERIFIED`; Codex-centered workflow `SUPPORTED`.

### 11. Runtime and Reporting Modularization; Tactics Q1-Q7

**Date / period:** `2026-05-15` through `2026-05-21`.

**Purpose:** reduce oversized runtime/reporting modules while retaining
behavior, then add a modular quant-tactic evidence layer.

**Major changes:** Commander/Scanner/Monitor and reporting hotspots were split
into focused runtime/report modules; tactic selection, cost floor, pullback,
runner-up, market/news evidence, and reporting surfaces were added across Q1-Q7.

**Affected components:** runtime orchestration, Monitor exit/entry helpers,
Scanner helpers, daily/metrics/trade reports, tactics docs and tests.

**Architecture impact:** increased module ownership and extension points without
removing compatibility paths.

**Primary agent / human role:** Codex-centered workflow `SUPPORTED`; individual
commit attribution `UNCERTAIN`.

**Verification:** broad regression tests recorded with the refactor and tactic
patches.

**Evidence:** `cf10d1c`, `bc150a6`, `docs/dev/incremental_refactor_plan_2026-05-15.md`,
`docs/tactics/quant_tactic_engine_phase_plan.md`.

**Confidence:** `VERIFIED` for changes, `SUPPORTED` for workflow attribution.

### 12. Q8 Tactical Validation and Q9 System Evaluation

**Date / period:** `2026-06-01` through `2026-06-26`.

**Purpose:** replace ad-hoc strategy patching with frozen evidence contracts and
then evaluate the complete agent chain.

**Major changes:** Q8 pullback/cost/runner-up/shadow validation; artifact trust
gates; Q8 closure; Q9 P/A/B/C decision windows; Top-K forward outcomes; Q10
Samsung/Hynix and Q11 opening controls; full-chain evaluation read models.

**Affected components:** tactics documentation, evaluation reporting, runtime
snapshots, baseline controls.

**Architecture impact:** tactics became lower-level evidence feeding a read-only
system-attribution layer.

**Primary agent / human role:** Codex-centered workflow `SUPPORTED`; specific
commits `UNCERTAIN`.

**Verification:** Q8/Q9 deterministic report and artifact tests.

**Evidence:** `ebddf7f`, `658a6d0`, `40b3c0d`, `docs/tactics`,
`docs/evaluation`. Some documents carry effective dates earlier than their Git
introduction date and must be labeled accordingly.

**Confidence:** implementation `VERIFIED`; exact document chronology
`SUPPORTED`.

### 13. Q13-Q18 Attribution and Bounded Promotion

**Date / period:** `2026-07-06` through `2026-07-30`.

**Purpose:** identify whether selection, Scanner alignment, entry timing, exit
horizon, or evidence quality caused poor outcomes, then permit at most one
bounded behavior patch.

**Major changes:** selection authority audit, scanner-score decomposition,
horizon compliance, entry timing, Attribution Score v0, Scanner root-cause
classification, Q15 candidate filtering, Q16 cost/horizon fit, Q17 directional
edge, Q18 post-reclaim review, same-symbol re-entry analysis, and integrity
cleanup.

**Affected components:** evaluation read models/reports, Q9 snapshots,
observation helpers, limited promoted runtime controls.

**Architecture impact:** separated diagnostic axes from behavior-change targets
and introduced frozen validation/promotion boundaries.

**Primary agent / human role:** Codex-centered workflow `SUPPORTED`; commit-level
agent attribution `UNCERTAIN`.

**Verification:** Q9/Q13/Q14/Q16 and cumulative regression tests.

**Evidence:** `0d80a6c`, `4fc3755`, `7bf5643`, `docs/q13`, `docs/q14`,
`docs/q13_q14_validation`.

**Confidence:** `VERIFIED`.

### 14. Offline Alpha, Horizon, and Agent Effectiveness

**Date / period:** `2026-07-30` through `2026-08-13`.

**Purpose:** exhaust retained evidence before collecting indefinite live
windows and connect selection, timing, horizon, repeated-symbol, and memory
questions.

**Major changes:** finite alpha hypothesis competition, opening Rank-1 research,
longitudinal/reactivation studies, horizon-revision backtest/runtime contract,
integrated quant diagnosis, agent-effectiveness scorecards, and memory integrity
reviews.

**Affected components:** `libs/research`, evaluation/reporting modules, horizon
runtime helpers, memory, docs.

**Architecture impact:** created an offline research layer isolated from trading
execution and a common evidence board for candidate promotion.

**Primary agent / human role:** Codex-centered workflow `SUPPORTED`; individual
implementation attribution `UNCERTAIN`.

**Verification:** deterministic research, horizon, memory, and diagnosis tests.

**Evidence:** `7bf5643`, `d5aaed6`, `8956a61`, `89f53fc`,
`docs/offline_alpha`, `docs/quant_trade_diagnosis`.

**Confidence:** `VERIFIED`.

### 15. Independent Web Observability and Controlled Validation

**Date / period:** `2026-08-14` through `2026-08-31`.

**Purpose:** expose operator-facing evidence without coupling the UI to trading
runtime, and run bounded mock-only validation lanes.

**Major changes:** FastAPI/React read-only console, Docker Compose isolation,
runtime status and host supervisor visibility, scheduled intelligence,
Cloudflare private ingress, operations command center, Alpha Research Board,
Q10/Q12 forward validation, controlled mock lanes, and point-in-time capture.

**Affected components:** `apps/api`, `apps/web`, `deploy`, scheduled reporting,
research/evaluation, controlled-lane runtime adapters.

**Architecture impact:** added an independently deployable read-only operations
plane while the Windows trading runtime remained outside Docker.

**Primary agent / human role:** branch and workflow evidence support a
Codex-centered workflow; individual commit implementation remains
`UNCERTAIN` unless separately recorded.

**Verification:** API/UI/isolation/deployment tests plus full Python regression.

**Evidence:** `759eafa`, `d9e22a3`, `ffd57a4`, `8894416`, `f7dac2f`,
`6aa4e39`, `docs/web_observability`.

**Confidence:** milestone `VERIFIED`; attribution `SUPPORTED`.

## Architecture Evolution

The evidence-backed sequence is:

```text
Pre-Git M1-M13 plans (chronology uncertain)
  -> V6 design-first agent/approval/execution foundation
  -> canonical Commander and skill/DTO boundaries
  -> resilience, persistent intent state, and idempotent execution
  -> portfolio/runtime/deployment governance
  -> operated M31 mock runtime
  -> explicit seven-agent roles and Reporter/memory visibility
  -> canonical event/artifact truth surfaces
  -> policy-aware ownership and deterministic reporting
  -> modular runtime/reporting and tactics evaluation
  -> Q8 tactical validation and Q9 system attribution
  -> Q13-Q18 root-cause and bounded promotion
  -> offline alpha/horizon/agent-effectiveness research
  -> independent read-only operations plane and controlled validation
```

## Historical, Target, and Current Architecture

### Historical Architecture

- The first Git snapshot already had agent separation, Supervisor approval,
  mock/real executors, and EventLog traceability.
- Multiple graph/legacy adapters and environment-owned policies accumulated as
  the system moved from plans to operation.
- Reporter and evaluation expanded from daily summaries into a large
  observability/research subsystem.

### Target Architecture

- Commander owns routing and canonical applied policy.
- Strategist proposes market/strategy policy and remains non-executing.
- Scanner owns candidate construction/ranking.
- Monitor owns selected-symbol entry/exit Intent generation.
- Supervisor approves; Executor applies deterministic guards and broker calls.
- Reporter/evaluation/memory remain evidence and advisory layers.
- Stable contracts and canonical artifacts isolate replaceable intelligence
  from execution safety.

### Current AS-IS at the Baseline

- `scripts/run_session.py` starts the integrated Commander runtime.
- `graphs/commander_runtime.py` contains canonical orchestration plus legacy and
  fast-path compatibility branches.
- Agent contracts and canonical artifacts exist, but policy ownership and some
  legacy field precedence remain additive migrations rather than a fully clean
  end state.
- Trading runtime runs as Windows host processes; the read-only API/UI runs in
  isolated Docker services.
- Q8-Q18 and offline-alpha outputs are evidence suppliers to the Alpha Research
  Board, not independent authorization to change trading behavior.

## Interpretation Rule

When documents conflict, do not silently choose the newest prose. Classify the
statement as historical design, target design, or current AS-IS, then verify the
current behavior in source and tests. Retrospective dates are effective dates,
not necessarily Git introduction dates.
