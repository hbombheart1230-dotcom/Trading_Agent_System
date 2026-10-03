# Pre-Claude Architecture Refactoring Baseline

## Baseline Identity

```text
Baseline:       Pre-Claude Architecture Refactoring
Date:           2026-08-31
Source Commit:  6aa4e398e2e1c33482cab3dbf2518e7b03c18a10
Development Era: Human + Codex-centered workflow
Status:         Current production/development AS-IS before Claude Code refactoring
Purpose:        Preserve historical state and enable comparison and rollback
Verification:   2701 passed, 1 skipped
```

At the time of capture:

- branch: `codex/observability-20260824`
- remote branch pointed to the same commit
- working tree was clean before this documentation work
- branch was 9 commits ahead of `main` and 0 behind
- no pre-Claude baseline Git tag existed

This document records the source baseline. It does not authorize a refactor and
does not alter trading behavior.

## Current System Definition

The baseline is a LangGraph-oriented seven-role trading system:

```text
Commander
  -> Strategist
  -> Scanner
  -> Monitor
  -> Supervisor
  -> Executor / Broker
  -> Reporter / Evaluation / Memory
```

The linear view is simplified:

- Commander owns orchestration, runtime routes, and applied-policy provenance.
- Strategist provides market/strategy frames and policy proposals.
- Scanner owns market candidate construction, scoring, ranking, and selection.
- Monitor evaluates selected/held symbols and emits entry/exit Intent.
- Supervisor owns approval and risk decisions.
- Executor applies deterministic guards and broker adapters.
- Reporter, evaluation, research, and memory consume evidence after or beside
  the execution path.

## Runtime AS-IS

- official entrypoint: `scripts/run_session.py`
- canonical orchestrator: `graphs/commander_runtime.py`
- active tick pipeline default: `integrated_chain`
- Windows host runtime: `scripts/run_m13_live_loop.py` backend with lock and
  heartbeat supervision
- phase model: preopen, session, closeout
- compatibility paths: legacy graph and adapter surfaces remain available
- trading state: persisted state plus broker/account truth readers

The current Commander is not a minimal state machine. It contains canonical
flow, fast paths, closeout/holding behavior, compatibility handling, policy
hydration, and evidence hooks. That is baseline reality, not a judgment that it
must all remain in one module.

## Contract and Truth AS-IS

Primary contract surfaces include:

- agent outputs: `libs/contracts/agent_outputs.py`
- Strategist output: `libs/strategies/contracts.py`
- Monitor Intent and decision packets: graph/risk contract modules
- intent lifecycle: `libs/supervisor/intent_state_store.py`
- canonical artifacts: `libs/runtime/canonical_artifacts.py`

Operational truth order is intended to be:

```text
Broker/account truth
  -> canonical per-run artifacts
  -> trade lifecycle bundle
  -> deterministic reports/read models
  -> LLM narrative and UI
```

Legacy readers and event-log fallbacks remain because migration was additive.
They must not silently override more authoritative evidence.

## Execution Safety AS-IS

- Monitor does not directly call the broker.
- Supervisor/decision approval is required before execution.
- Executor guards can reject an approved Intent.
- mock and real broker adapters are separated by runtime configuration.
- persistent Intent state and CAS claims provide idempotency support.
- duplicate/recent-order, portfolio, symbol, asset, cash, closeout, and
  monitor-exit guards exist in `execute_from_packet` and supporting modules.
- controlled Q10/Q12 lanes remain Kiwoom-mock-only and use the existing
  approval/Executor path.

This baseline does not certify real-money readiness. It records the current
guarded execution design and its tested behavior.

## Observability and Evaluation AS-IS

- append-only runtime events are organized around `run_id`.
- per-agent canonical artifacts are written below `reports/canonical`.
- trade lifecycle/report bundles are written below `reports/trades`.
- Q8-Q18 evaluation and offline-alpha research are read-only evidence layers
  except for separately documented controlled promotions.
- Alpha Research Board is the closeout-level research authority.
- deterministic facts are intended to precede LLM narrative.
- runtime memory is advisory and records provenance/effectiveness surfaces.

## Web and Deployment AS-IS

- FastAPI and React provide an independent read-only operations console.
- Docker Compose starts the read-only API and Web gateway, not Trading Runtime.
- report/data mounts are read-only.
- optional Cloudflare Tunnel publishes only the Web gateway behind Access.
- host supervisor controls are bounded and exposed through a dedicated
  operations contract; the Web UI does not become trading execution authority.

## Strategy and Research AS-IS

- Strategist LLM is a structured proposal source, not broker authority.
- Scanner and Monitor retain deterministic scoring/gate logic.
- Q8 is closed as tactical validation history.
- Q9-Q18 provide attribution, bounded promotion, and integrity evidence.
- Q10 Samsung/Hynix, Q11 opening, and Q12 BTC/Woori tracks are independent
  controls/validation lanes.
- offline-alpha research uses fixed hypotheses and separates historical
  discovery from prospective evidence.
- current controlled probes are mock-only and bounded by lane/day rules.

## Verification Snapshot

The full Python suite executed at source commit `6aa4e39` with:

```text
2701 passed, 1 skipped
```

Repository inventory at investigation time:

- 374 commits
- 423 test files
- approximately 2,688 Python test definitions
- 654 documentation files
- 1,458 Python files

These counts describe scale; they are not a quality score or attribution proof.

## Known Architecture Debt

The following are baseline debt or audit targets. They are not fixed by this
documentation work and are not considered true merely because a future AI audit
mentions them.

### 1. Canonical Orchestrator Size and Mixed Responsibilities

`graphs/commander_runtime.py` remains large and combines routing, compatibility,
policy hydration, fast paths, evidence hooks, and operational decisions.

**Status:** known debt; exact extraction boundaries require audit and regression
evidence.

### 2. Legacy and Canonical Paths Coexist

Legacy adapters, graph nodes, environment aliases, fallback readers, and
canonical modules coexist by additive-migration policy.

**Risk:** ambiguous ownership or precedence if a consumer chooses the wrong
surface.

**Status:** known debt; do not delete without consumer and test inventory.

### 3. Policy Ownership Is Not Uniformly Pure

Target architecture assigns proposal ownership to Strategist and applied-policy
ownership to Commander, but legacy gates and environment-backed defaults still
participate in behavior.

**Status:** known mismatch between target and AS-IS; requires code-level audit.

### 4. Reporter and Evaluation Surface Is Large

Reporting, reconciliation, evaluation, research, and memory modules have grown
substantially. Similar truth resolution can exist at multiple levels.

**Risk:** duplicated interpretation, schema drift, or inconsistent precedence.

**Status:** known debt; deterministic truth ownership must be mapped before
refactoring.

### 5. Documentation Has Multiple Eras

Historical plans, target architecture, current AS-IS, patch notes, and later
retrospectives coexist. Some effective dates predate their Git introduction.

**Risk:** treating a target plan as implemented state or a retrospective date as
commit chronology.

**Status:** provenance debt addressed partially by this documentation set.

### 6. Patch-Note Integrity Is Incomplete

The structured patch-note history has useful coverage but includes pre-Git
reconstruction, missing source references, and an 8/31 Markdown-only entry at
the source baseline.

**Status:** historical entries remain untouched; this baseline adds one
traceable provenance entry only.

### 7. Branch and Main Differ

The source baseline branch is nine commits ahead of `main`.

**Risk:** a refactor started from `main` would omit recent observability,
controlled-validation, and Q10/Q12 work.

**Status:** refactoring must start from the explicit baseline commit/tag.

### 8. Generated Runtime Evidence Is Not Git History

Reports, state, logs, broker snapshots, and scheduled artifacts are operational
evidence but are largely excluded from Git.

**Risk:** code archaeology alone cannot reconstruct every live incident or
validation result.

**Status:** retain artifacts separately when required for audit.

### 9. Test Volume Does Not Prove Architecture Correctness

The large regression suite strongly constrains behavior but can preserve legacy
coupling or outdated policy assumptions.

**Status:** audit tests for contract authority and behavior before structural
changes; do not equate test count with design fitness.

## Future Audit Finding Policy

A Claude Code, Codex, or Human audit finding must be classified as one of:

- `CONFIRMED`: reproduced against source, contract, test, or artifact
- `NOT_REPRODUCED`: insufficient current evidence
- `DESIGN_QUESTION`: valid ambiguity without demonstrated defect
- `ACCEPTED_RISK`: confirmed but intentionally retained

Audit origin is provenance, not proof. A confirmed finding should cite the
baseline commit and exact evidence.

## Refactoring Boundary

No source, runtime, strategy, execution, guard, DTO, or test behavior was
changed to create this baseline documentation. Refactoring must be performed on
a new explicitly named branch from the approved baseline ref and reviewed
against this AS-IS record.
