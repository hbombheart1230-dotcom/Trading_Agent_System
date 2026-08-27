# M7.3 Scheduled Intelligence and Memory Delivery Visibility

Date: 2026-08-27

## Purpose

Expose the existing 08:50 Preopen and 16:00 Closeout results as trustworthy,
human-readable scheduled intelligence without adding a second scheduler, a
second memory system, or another LLM call.

## Non-Duplication Rule

The implementation reuses the existing authorities:

* Preopen macro capture and Stage-1 Strategist output;
* Closeout Kiwoom account snapshot and broker reconciliation;
* operator daily summary and system health;
* post-exit and evaluation outputs;
* `reports/performance/YYYY-MM-DD/strategy_memory.json`.

It does not recalculate PnL, re-run evaluation logic, call Codex, call a new
LLM, or feed the rendered Markdown back into Strategist.

## Runtime Flow

```text
08:50 existing Preopen task
  -> macro snapshot
  -> existing preopen Strategist
  -> additive scheduled-intelligence materializer
  -> preopen manifest, briefing and memory delivery receipt

16:00 existing Closeout task
  -> existing broker/report/evaluation/memory pipeline
  -> additive scheduled-intelligence materializer
  -> closeout manifest and daily intelligence index
```

The Preopen materializer never changes the original Preopen return code. The
Closeout materializer is isolated from the existing Closeout success decision
and records its own failure if projection generation fails.

## Artifacts

```text
reports/runtime/scheduled_jobs/YYYY-MM-DD/preopen.json
reports/runtime/scheduled_jobs/YYYY-MM-DD/closeout.json
reports/runtime/scheduled_jobs/latest_preopen.json
reports/runtime/scheduled_jobs/latest_closeout.json

reports/briefings/YYYY-MM-DD/preopen_briefing.json
reports/briefings/YYYY-MM-DD/preopen_briefing.md
reports/briefings/YYYY-MM-DD/memory_delivery_receipt.json
reports/briefings/YYYY-MM-DD/daily_intelligence_index.json
reports/briefings/YYYY-MM-DD/daily_intelligence_index.md
```

## Memory Delivery Semantics

| Status | Meaning |
| --- | --- |
| `DELIVERED_ACTIVE` | Memory was present in Strategist input and at least one deterministic memory layer was active. |
| `DELIVERED_ADVISORY` | Memory was present in Strategist input, but deterministic memory layers were inactive/surface-only. |
| `NOT_CONFIRMED` | The Strategist artifact does not prove memory delivery. |

The 2026-08-27 Preopen receipt is `DELIVERED_ADVISORY`: the 2026-08-26
strategy memory was present in Strategist input, while daily, weekly and
monthly packets reported `active=false` and Commander memory application mode
was `surface_only`. The UI must not present this as active policy application.

## API and UI

```text
GET /api/v1/runtime/scheduled-intelligence
```

The route is read-only and returns no report body, prompt, credentials,
process-control action, or order action. Overview shows:

* expected and actual Preopen/Closeout time;
* success, partial, failed, or not-run status;
* memory delivery status and source day;
* compact market/strategy summary;
* explicit issues.

## Failure Semantics

* Macro capture failure plus successful Strategist is `PARTIAL`, not hidden.
* Missing Strategist artifact is `FAILED` or `MISSING_ARTIFACT`.
* Missing memory proof becomes `NOT_CONFIRMED`.
* Re-materialization preserves the original Strategist completion time and
  records materialization time separately.
* A failed projection does not change trading behavior or overwrite existing
  source artifacts.

## Verification

Live 2026-08-27 Preopen:

```text
manifest: SUCCESS
macro capture: SUCCESS
Strategist: SUCCESS
model: deepseek/deepseek-v3.2
memory source: 2026-08-26
memory delivery: DELIVERED_ADVISORY
issues: none
```

Historical 2026-08-26 Closeout was re-materialized successfully from existing
artifacts and linked Broker Truth, reconciliation, operator summary, system
health, post-exit, evaluation and strategy-memory outputs.

Focused verification:

```text
Python/API: 76 passed, 1 skipped
Web unit: 14 passed
Strict TypeScript and production Docker build: passed
Clean Main restart: RUNNING, one logical session, fresh heartbeat, empty stderr
```

Final repository regression after the live restart:

```text
Python: 2646 passed, 1 skipped
Web unit: 14 passed
Runtime: RUNNING, one logical session, NORMAL_PROCESS_TREE
Watchdog supervisor: NOOP / runtime_healthy
```
