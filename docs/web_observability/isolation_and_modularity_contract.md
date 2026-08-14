# UI Isolation and Modularity Contract

## 1. Authority

This contract is mandatory for every implementation under:

```text
apps/api/**
apps/web/**
deploy/**
tests/apps/**
docs/web_observability/**
```

The first priority is that Web/API work must never affect the active Trading
Runtime. Feature delivery is subordinate to runtime isolation.

## 2. Runtime Isolation Invariants

The Web/API platform must:

* run as separate operating-system processes and separate containers;
* use a separate dependency manifest from the Trading Runtime;
* never be launched by `restart_live_session.bat` or the live-session process
  tree;
* never import or initialize Trading Core, evaluation executors, broker clients,
  LLM clients, graphs, Commander, Scanner, Strategist, Monitor, or Executor;
* never call Kiwoom or any order API;
* never acquire or modify Trading Runtime lock/state files;
* never write to `reports/**`, `data/logs/**`, `data/state/**`, or `.env`;
* expose GET-only HTTP routes;
* treat every evidence path as an immutable external input;
* continue to fail independently when the Trading Runtime is unavailable;
* never restart, stop, signal, or health-gate the Trading Runtime.

Docker and Kubernetes must mount all Trading evidence as read-only. Trading
Core source, credentials, `.env`, and execution modules must not be copied into
the API/Web images.

## 3. Resource Isolation

Read-only is not sufficient if observation consumes enough I/O, CPU, or memory
to disturb trading. The implementation must also enforce:

* no request-time full scan of multi-GB JSONL files;
* bounded tail reads for recent events;
* bounded date ranges and result counts;
* size limits before opening report detail;
* in-process read cache with a short TTL for repeatedly requested summaries;
* concurrency limits and request timeouts;
* one replica in the local Kubernetes environment;
* explicit CPU and memory limits for API and Web containers;
* no filesystem watcher that recursively watches all of `reports/**` or
  `data/logs/**`;
* no polling interval below the documented minimum for a data class;
* graceful `PARTIAL`, `STALE`, or `UNAVAILABLE` responses instead of expensive
  fallback reconstruction.

The UI must not make the API recompute Q9-Q18 evaluations. It reads completed
artifacts only.

## 4. Backend Module Boundaries

Backend code follows this one-way dependency flow:

```text
router
  -> application service
    -> domain read model / aggregation
      -> source adapter
        -> read-only filesystem utility
```

Dependencies must not flow upward or sideways across unrelated features.

### 4.1 Source Adapters

One adapter family owns one source contract:

```text
apps/api/adapters/
  kiwoom/
  operator_summary/
  trade_reports/
  evaluation/
  offline_alpha/
  market/
```

Responsibilities:

* parse one source schema;
* normalize missing, malformed, stale, and unknown fields;
* attach provenance and freshness;
* perform no cross-source aggregation;
* perform no HTTP response formatting.

### 4.2 Domain Read Models

Read models are broker- and Q-phase-neutral:

```text
Trade
Portfolio
PerformanceSummary
PerformanceSeries
Opportunity
StrategyBreakdown
MarketSnapshot
DataQualityIssue
```

They contain no Kiwoom TR field names and no Q9/Q13 schema-specific field names.

### 4.3 Aggregators

Each aggregation dimension is independently testable. Examples:

```text
performance/
  pnl.py
  costs.py
  win_loss.py
  drawdown.py
  holding_time.py
  breakdowns.py

opportunities/
  funnel.py
  topk.py
  blockers.py
  forward_paths.py
  missed_opportunity.py
```

Aggregators are pure where possible: structured input in, structured output
out, with no hidden filesystem access.

### 4.4 Services and Routers

* A service composes only the read models needed by one product use case.
* A router validates HTTP input and returns a response model.
* Routers do not parse files, aggregate metrics, or know artifact paths.
* Services do not import other feature routers or UI concepts.
* Shared helpers are introduced only for genuinely shared infrastructure such
  as bounded reads, time parsing, provenance, and response status.

## 5. Frontend Module Boundaries

Frontend code is split by product feature, not by one global component folder.

```text
apps/web/src/
  app/
  shared/
    api/
    charts/
    formatters/
    layout/
    states/
  features/
    overview/
    performance/
    trades/
    opportunities/
    strategies/
    market/
    reports/
    data-quality/
```

Each feature may contain:

```text
api.ts
types.ts
queries.ts
selectors.ts
components/
pages/
tests/
```

Rules:

* pages compose feature components but do not calculate financial metrics;
* API response normalization stays in feature API/selectors;
* charts receive display-ready series and do not read global raw responses;
* loading, partial, unavailable, no-data, stale, and error states use shared
  primitives;
* cross-feature imports go through explicit public exports;
* no single global store contains every raw artifact;
* raw logs, absolute paths, Q-phase payloads, and broker fields do not leak into
  presentational components.

## 6. File Size and Responsibility Rule

Small files are preferred, but line count alone is not the goal. A file should
have one reason to change.

Split a file when it combines any of these responsibilities:

* filesystem access and aggregation;
* schema normalization and product interpretation;
* multiple unrelated API endpoints;
* data fetching and complex presentation;
* several independent chart/table calculations;
* internal operation and public portfolio redaction;
* feature logic and infrastructure configuration.

During review, files approaching roughly 300 lines require an explicit reason
to remain together. Generated files, schemas, fixtures, and simple declarative
tables are exceptions. This is a review trigger, not an automatic rewrite rule.

## 7. Change Scope Rule

Implementation defaults to new files within the approved paths.

Changes are forbidden in:

```text
libs/agent/**
libs/execution/**
graphs/**
scripts/**
apps/operator_ui/**
existing evaluation calculation code
existing report/log schemas
existing Trading Runtime configuration
```

If a desirable UI feature appears to require a Core change:

1. do not make the change;
2. mark the UI field `UNAVAILABLE` or `PARTIAL`;
3. document the missing source contract;
4. continue with independent features;
5. review the proposed Core change separately after market operation.

## 8. Mandatory Tests and Gates

Every implementation milestone must prove:

* forbidden import scan passes;
* only GET routes exist;
* test fixtures use temporary directories;
* no evidence or state path is writable through the API;
* malformed files do not crash unrelated panels;
* path traversal is rejected;
* file-size and result-count limits work;
* large-file tests demonstrate bounded reads;
* services and aggregators are deterministic;
* public portfolio output removes account/order/path/prompt identifiers;
* Trading Runtime process, lock, heartbeat, and artifact cadence are unchanged
  before and after an API/UI smoke test.

Before and after each milestone, record but do not mutate:

```text
Trading Runtime PID
heartbeat age
events update cadence
Q9 decision-window update cadence
CPU and memory of Trading Runtime
```

Any measurable runtime interference blocks the milestone.

## 9. Implementation Review Checklist

Before merging a slice:

1. Is this a new isolated module?
2. Does it have one responsibility?
3. Can it be tested without the live repository data?
4. Does it use a source adapter instead of parsing in the router/UI?
5. Is every read bounded?
6. Can a malformed source fail only its own panel?
7. Is there any import or process path back to Trading Core?
8. Is there any write, lock, network, or execution side effect?
9. Does the UI expose business meaning rather than internal Q schema?
10. Did the Trading Runtime heartbeat and cadence remain normal?

If any answer is unsatisfactory, the slice is not complete.
