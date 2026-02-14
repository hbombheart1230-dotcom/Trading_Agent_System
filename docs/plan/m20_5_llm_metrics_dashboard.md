# M20-5: Strategist LLM Metrics Summary in Daily Metrics Report

- Date: 2026-02-14
- Goal: include strategist LLM reliability metrics in the existing metrics report output (JSON + markdown).

## Scope

1. Extend `generate_metrics_report.py` with `strategist_llm` aggregate metrics.
2. Add tests for LLM metric aggregation and empty-report schema stability.
3. Update roadmap/observability/project-tree docs.

## Implemented Changes

### 1) Metrics aggregation extension

File:
- `scripts/generate_metrics_report.py`

Changes:
- Added `strategist_llm` summary block in JSON output:
  - `total`
  - `ok_total`
  - `fail_total`
  - `success_rate`
  - `latency_ms` (count/avg/p50/p95/max)
  - `attempts` (count/avg/p50/p95/max)
  - `error_type_total`
- Added markdown section:
  - Strategist LLM totals/success-rate
  - latency summary (ms)
  - attempts summary
  - errors by type
- Preserved existing execution and API error metric fields.

### 2) Test coverage

File:
- `tests/test_generate_metrics_report.py`

Coverage:
- strategist LLM aggregation (success/fail/latency/attempts/error type)
- empty report includes `strategist_llm` keys with zero defaults
- existing core metric expectations remain intact

## Validation Result

- Command:
  - `.\venv\Scripts\python.exe -m pytest -q tests/test_generate_metrics_report.py tests/test_m20_4_llm_ops_scripts.py tests/test_m20_3_legacy_llm_router_compat.py tests/test_m20_3_llm_event_logging.py tests/test_m20_2_decide_trade_llm_flow.py tests/test_m20_1_openai_provider_smoke.py`
- Result:
  - `23 passed`

## Safety Notes

- No execution, guard precedence, or approval path logic changed.
- Scope is observability/reporting only.
