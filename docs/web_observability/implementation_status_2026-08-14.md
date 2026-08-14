# Web Observability Implementation Status - 2026-08-14

## Current Milestone

| Milestone | Status | Notes |
| --- | --- | --- |
| M0 Product/Data Contract | Complete | Truth, time, cost, metric, availability contracts frozen |
| M1 Read-only API Foundation | Complete | Isolated FastAPI health/config/path/bounded-read foundation |
| M2 Performance API | Complete | Overview, portfolio, trusted net performance, PnL series, and cost availability |
| M3 Trades/Reports API | Complete | Trade list/detail/timeline, performance fallback, safe report access |
| M4 Opportunities/Strategies/Market API | Complete | Generic opportunity, strategy, and market read models |
| M5 Web UI MVP | Complete | Nine-domain React/Vite operating console running locally |
| M5.1 LLM Operations | Complete | OpenRouter role, model, stage, status, and bounded-latency surface |
| M6 Public mode and anomaly surface | Complete | Explainable anomaly read model and server-enforced sanitized showcase profile |
| M7 Docker Compose | Prerequisite pending | Host is suitable; WSL2 and Docker Desktop are not installed |
| M8 Kubernetes local overlay | Not started | Begins only after M7 local Compose passes |
| M9 Integrated audit | Not started | Final observability audit after M7-M8 |

## M1 Added Surface

```text
apps/api/
  config.py
  main.py
  infrastructure/
    bounded_reader.py
    paths.py
    source_roots.py
  models/
    common.py
    health.py
  routers/
    health.py
  services/
    health.py
```

Endpoints:

```text
GET /health/live
GET /health/ready
```

No API server was left running. Validation used in-process FastAPI test clients
only.

## Isolation Result

* Trading Core imports: 0
* existing evaluation imports: 0
* existing Operator UI imports: 0
* network/broker/LLM imports: 0
* filesystem write calls: 0
* non-GET API routes: 0
* existing Trading Runtime files changed by tests: 0

The source-root response exposes logical names only (`reports`, `logs`,
`state`). It does not expose absolute host paths.

## Verification

```text
new API tests: 13 passed, 1 skipped
existing Operator UI regression: 51 passed
compileall apps/api: passed
```

The skipped test is the Windows symlink-escape test because the current user
cannot create the test symlink. Normal traversal and absolute-path tests pass,
and `Path.resolve()` plus root-relative validation implements the same runtime
guard.

## Live Runtime Non-Interference Check

Before:

```text
captured: 09:38:29 KST
Trading Runtime PID: 760
events.jsonl size: 866,277,396
Q9 decision-window size: 4,657,355
working set: 185,712,640 bytes
```

After:

```text
captured: 09:43:20 KST
Trading Runtime PID: 760
process responding: true
events.jsonl size: 867,057,791
Q9 decision-window size: 5,400,401
working set: 188,522,496 bytes
```

The PID remained unchanged, heartbeat remained active, and both live evidence
streams continued to grow during tests. No API background process was started.

## Dirty Worktree Boundary

The following paths existed as unrelated uncommitted work before M1 and were
not modified as part of the Web/API implementation:

```text
docs/runtime_memory/**
libs/reporting/evaluation/memory_review/**
scripts/run_memory_contamination_review.py
tests/test_memory_contamination_review.py
```

Future Web/API scope audits must compare against this baseline instead of
treating those pre-existing paths as changes made by the observability work.

## M2 Added Surface

M2 is complete. It added the following isolated API surface:

```text
GET /api/v1/overview?day=YYYY-MM-DD
GET /api/v1/portfolio?day=YYYY-MM-DD
GET /api/v1/performance/summary?start=YYYY-MM-DD&end=YYYY-MM-DD
GET /api/v1/performance/series?start=YYYY-MM-DD&end=YYYY-MM-DD
```

M2 uses `performance_summary.v1` rows whose `return_basis` is
`truth_surface_net`. It does not merge lifecycle-only or observed shadow
returns into realized performance. Period results deduplicate `trade_id`.

Supported result basis:

```text
MOCK_BROKER_NET: available when truth-surface samples exist
GROSS: unavailable from the current source
LIVE_EQUIVALENT_NET: unavailable from the current source
```

Absolute realized PnL is exposed only when the trusted trade row contains
`pnl`. Gross PnL, explicit total cost, cost drag, and current open orders remain
`UNAVAILABLE`; they are never represented as zero.

Portfolio data is projected from the daily operator summary's reconciled
residual-position read model. The raw Kiwoom account snapshot is not read by
request handlers because the audited files can contain invalid JSON after
legacy Korean-title encoding corruption. See
`m2_source_audit_2026-08-14.md`.

## M2 Verification

```text
Web/API tests: 24 passed, 1 skipped
existing Operator UI regression: 51 passed
compileall apps/api: passed
actual 2026-06-01..2026-07-31 read: 110 trades, 81 trusted returns
actual 2026-08-01..2026-08-13 series: NO_DATA, not a fabricated zero return
```

M2 verification used in-process clients only. No API server or background job
was started.

Live-runtime comparison after M2:

```text
Trading Runtime PID: 760 (unchanged)
process responding: true
heartbeat active: true
events.jsonl grew from 867,487,495 to 870,112,893 bytes
working set: 193,662,976 bytes
```

## Next Gate

M3 is complete. It added:

```text
GET /api/v1/trades
GET /api/v1/trades/{trade_id}
GET /api/v1/trades/{trade_id}/reports
GET /api/v1/trades/{trade_id}/reports/{report_id}
```

The list and detail surfaces provide symbol identity, themes, broker-net
result, strategy/tactic/horizon, Scanner rank, entry/hold/exit timeline,
post-exit checkpoints, agent-source integrity, and evaluation exclusion state.

M3 never reads these large or sensitive source families:

```text
lifecycle_bundle.json
ai_trade_report_input.json
raw LLM response JSON
events.jsonl
```

Report access uses fixed identifiers. Arbitrary relative paths are not accepted,
host paths are redacted, JSON path/prompt/response/order fields are removed,
and report reads remain size-bounded.

## M3 Verification

```text
Web/API tests: 35 passed, 1 skipped
existing Operator UI regression: 51 passed
compileall apps/api: passed
actual 2026-06-01..2026-07-31 trade list: 110 rows
trade bundle rows: 86
performance fallback rows: 24
fully available display rows: 8
partial display rows: 102
```

The API preserves all 110 performance-ledger trade identities instead of
silently dropping the 24 rows without a usable trade bundle. Fallback rows are
explicitly labeled `PERFORMANCE_FALLBACK` and do not fabricate a timeline.
See `m3_trade_source_audit_2026-08-14.md`.

## M4 Added Surface

```text
GET /api/v1/opportunities/funnel
GET /api/v1/opportunities/outcomes
GET /api/v1/strategies/performance
GET /api/v1/market/snapshot
GET /api/v1/market/series
```

Opportunity responses distinguish shadow/observation evidence from realized
performance and retain gross, live-equivalent, and mock-broker cost surfaces.
Strategy performance reuses the M3 normalized trade read model. Market APIs
read only bounded daily macro snapshots and never call external providers.

## M4 Verification

```text
Web/API tests: 43 passed, 1 skipped
existing Operator UI regression: 51 passed
compileall apps/api: passed
actual 2026-08-13 opportunity signals: 168 total, 3 current symbols
actual 2026-08-13 opening outcomes: 8 rows, 39/40 checkpoints observed
actual 2026-06-01..2026-07-31 strategy rows: 110 trades
actual 2026-08-14 market metrics: 15/15 available
```

See `m4_opportunity_strategy_market_source_audit_2026-08-14.md` for authority,
coverage, and request-time exclusion details.

M5 is the next gate. It builds the independent Web UI over the frozen M0-M4
API contracts. It must remain operational and presentation focused rather than
becoming an evaluation-progress dashboard.

## M5 Added Surface

M5 adds `apps/web` with eight product pages:

```text
Overview
Performance
Trades
Opportunities
Strategies
Market
Reports
Data Quality
```

The Web uses React, TypeScript, Vite, Lucide icons, and Recharts. Feature pages
are lazy-loaded and split by domain. There are no mutation controls or direct
artifact reads.

## M5 Verification

```text
Web unit tests: 3 passed
Web strict TypeScript and production build: passed
Browser smoke: 16 desktop/mobile route renders passed
Console/page errors: 0
Horizontal document overflow: 0
API readiness through Web proxy: AVAILABLE
```

Local processes were started without restarting Trading Runtime:

```text
Web: http://127.0.0.1:5173
API: http://127.0.0.1:8000
```

See `m5_web_ui_implementation_2026-08-14.md` for the screen, module, safety,
and verification details.

## M5.1 LLM Operations

M5.1 adds a ninth `LLM Operations` page and a single read-only endpoint:

```text
GET /api/v1/llm/operations?day=YYYY-MM-DD
```

Daily call/model/status authority comes from stage-specific `reports/llm`
artifacts. Recent latency comes from a bounded event-log tail. Missing token
and cost fields remain unavailable rather than becoming false zero values.

The page explicitly distinguishes configured models from selected-day observed
models and reports the current trade-report MiniMax/Nemotron route mismatch.
No prompts, response text, credentials, or internal paths are returned.

See `m5_1_llm_operations_implementation_2026-08-14.md` for the complete source,
availability, UI, and verification contract.

## M6 Anomaly and Public Profile

M6 adds:

```text
GET /api/v1/anomalies?day=YYYY-MM-DD
GET /api/v1/profile
```

The anomaly surface detects runtime freshness, artifact-integrity warnings,
cost-drag spikes, same-symbol repeated losses, sub-60-second loss exits, and
observed shadow opportunity misses. It is explicitly observation-only and
returns its evidence and fixed threshold with every signal.

The public profile is selected server-side with
`OBSERVABILITY_EXPOSURE_PROFILE=public`. It preserves the private profile's
metric formulas, identifies all results as simulation/mock, blocks report
content before reading it, removes sensitive identifiers and values from JSON,
and hides private-only navigation.

Implementation and policy details are fixed in
`m6_anomaly_public_profile_implementation_2026-08-14.md`.

## M6 Verification

```text
API regression: 57 passed, 1 skipped
Web unit tests: 3 passed
Strict TypeScript and production build: passed
Browser smoke: 10 routes x desktop/mobile = 20 renders passed
Public-profile navigation/mode browser check: passed
Trading Core imports from apps/api: 0
non-GET routes: 0
filesystem write-call isolation scan: passed
```

Actual artifact smoke:

```text
2026-07-21 trades evaluated: 1
warnings classified: 2
categories: COST_SPIKE, EARLY_LOSS_EXIT
policy: operational_anomaly.v1
```

Live-runtime comparison:

```text
before event size: 908,210,563 bytes at 12:52:02 KST
after event size:  909,484,892 bytes at 13:00:06 KST
Trading Runtime PID: 760 before and after
Trading Runtime responding: true
API profile after verification: private
API readiness: AVAILABLE
Web/API listeners: 127.0.0.1:5173 and 127.0.0.1:8000
```

The API process was replaced to load M6. The Trading Runtime and Web process
were not restarted.

## M7 Weekend Gate

The 2026-08-14 host audit confirmed Windows 11 Home 64-bit, 15.5 GB memory,
220.2 GB free storage, and an active hypervisor. WSL, Docker Desktop, Docker
CLI, and Docker Compose are not installed.

M7 therefore starts after market close with administrator WSL installation,
restart, Docker Desktop installation, and CLI verification. M7 includes only
Web and read-only API containers. Trading Runtime remains on the Windows host
through M9 and may enter a separate shadow-first container migration track
afterward.

See `m7_prerequisites_and_weekend_plan_2026-08-14.md` for the fixed weekend
work slices, external-access boundary, and future runtime migration gates.
