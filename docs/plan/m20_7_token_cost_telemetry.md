# M20-7: Strategist LLM Token/Cost Telemetry

- Date: 2026-02-14
- Goal: add token usage and estimated cost observability for strategist LLM runs without changing execution safety behavior.

## Scope

1. Extract token usage from strategist provider responses.
2. Estimate per-call LLM cost from env-configured token prices.
3. Propagate token/cost fields to `strategist_llm` telemetry events.
4. Extend ops scripts and daily metrics report with token/cost aggregates.

## Implemented Changes

### 1) Provider usage extraction and cost estimation

File:
- `libs/ai/providers/openai_provider.py`

Changes:
- Added response usage extraction:
  - `prompt_tokens`
  - `completion_tokens`
  - `total_tokens` (derived when missing and prompt/completion exist)
- Added env-configurable token price parsing:
  - `AI_STRATEGIST_PROMPT_COST_PER_1K_USD`
  - `AI_STRATEGIST_COMPLETION_COST_PER_1K_USD`
- Added per-call estimated cost calculation:
  - `estimated_cost_usd`
- Included extracted usage/cost fields in provider `meta`.

### 2) Event payload extension (`strategist_llm/result`)

File:
- `graphs/nodes/decide_trade.py`

Changes:
- Added telemetry payload fields:
  - `prompt_tokens`
  - `completion_tokens`
  - `total_tokens`
  - `estimated_cost_usd`

### 3) Ops visibility extension

Files:
- `scripts/smoke_m20_llm.py`
- `scripts/query_strategist_llm_events.py`

Changes:
- Smoke summary now prints token/cost fields for latest strategist LLM event.
- Query human-readable output now includes token/cost fields per row.

### 4) Metrics report aggregation

File:
- `scripts/generate_metrics_report.py`

Changes:
- Added strategist LLM token/cost summary block:
  - `token_usage.prompt_tokens_total`
  - `token_usage.completion_tokens_total`
  - `token_usage.total_tokens_total`
  - `token_usage.estimated_cost_usd_total`
- Added markdown section: `Token Usage and Cost`.

## Tests

Updated files:
- `tests/test_m20_1_openai_provider_smoke.py`
- `tests/test_m20_3_llm_event_logging.py`
- `tests/test_m20_4_llm_ops_scripts.py`
- `tests/test_generate_metrics_report.py`

Validation command:
- `python -m pytest -q tests/test_m20_1_openai_provider_smoke.py tests/test_m20_2_decide_trade_llm_flow.py tests/test_m20_3_llm_event_logging.py tests/test_m20_3_legacy_llm_router_compat.py tests/test_m20_4_llm_ops_scripts.py tests/test_generate_metrics_report.py`

Validation result:
- `26 passed`

## Safety Notes

- No execution path or guard precedence was changed.
- Token/cost tracking is observability-only and can be disabled by leaving token price env vars at defaults (`0`).
