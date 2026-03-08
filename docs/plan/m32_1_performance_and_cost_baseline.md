# M32-1 Performance and Cost Baseline (Preparation Note)

- Date: 2026-03-08
- Scope: define baseline measurement plan only (no full M32 implementation yet).

## Baseline Goal

Establish one reproducible baseline dataset for:

- p95 runtime latency
- strategist LLM latency
- cost per run
- cost per intent
- broker/API `429` rate

## Current Source of Truth

1. Event log
- `data/logs/events.jsonl`
- primary events:
  - `stage=strategist_llm, event=result`
  - `stage=decision, event=trace`
  - `stage=execute_from_packet, event=verdict|execution`

2. Metrics report generator
- `scripts/generate_metrics_report.py`
- already computes:
  - `execution_latency_seconds` summary (`avg/p50/p95/max`)
  - strategist `latency_ms` summary
  - token totals (`prompt/completion/total`)
  - `estimated_cost_usd_total`
  - broker `api_429_rate`

3. Operator summary
- `libs/reporting/operator_visibility.py`
- used for human-layer status and incident visibility.

## Required Measurement Definitions

1. Runtime p95 latency
- source: `execution_latency_seconds.p95`
- definition: per-run wall-clock latency across core runtime cycle.

2. Strategist p95 latency
- source: `strategist_llm.latency_ms.p95`
- definition: provider call latency (including retries when surfaced).

3. Cost per run
- definition: `estimated_cost_usd_total / run_total`
- run count source: unique `run_id` for target day.

4. Cost per intent
- definition: `estimated_cost_usd_total / intents_created`
- intent count source: `execution.intents_created`.

5. API 429 rate
- source: `broker_api.api_429_rate`
- definition: `api_429_total / api_error_total`.

## Hot-path Latency Measurement Points

1. `run_m13_tick` cycle start/end (runtime envelope)
2. strategist call boundary:
- before `strategist.decide`
- after `strategist.decide`
3. decision-to-verdict boundary
4. verdict-to-execution boundary

## Patch Plan (Next, Minimal)

1. Add one M32 baseline script:
- `scripts/run_m32_performance_cost_baseline.py`
- inputs: `event_log_path`, `day`, optional output dir
- outputs:
  - `reports/m32_baseline/m32_baseline_<day>.json`
  - `reports/m32_baseline/m32_baseline_<day>.md`

2. Add deterministic tests:
- `tests/test_m32_performance_cost_baseline.py`
- validate metric math and missing-data behavior

3. Integrate into closeout chain as optional step
- no blocking gate initially
- additive artifact only

## Out of Scope (This Step)

- prompt/model optimization rollout
- retry policy redesign
- caching strategy changes
- runtime concurrency redesign
