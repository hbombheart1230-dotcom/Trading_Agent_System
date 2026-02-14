# M20-6: Prompt/Schema Version Telemetry for Strategist LLM

- Date: 2026-02-14
- Goal: make LLM behavior auditable by attaching `prompt_version` and `schema_version` to strategist telemetry and metrics.

## Scope

1. Add prompt/schema version config to strategist provider.
2. Propagate version fields to `strategist_llm` event payloads.
3. Extend metrics report with version distribution aggregates.
4. Update tests and docs.

## Implemented Changes

### 1) Provider version config and meta propagation

File:
- `libs/ai/providers/openai_provider.py`

Changes:
- Added provider defaults:
  - `DEFAULT_PROMPT_VERSION="m20-6"`
  - `DEFAULT_SCHEMA_VERSION="intent.v1"`
- Added env parsing:
  - `AI_STRATEGIST_PROMPT_VERSION`
  - `AI_STRATEGIST_SCHEMA_VERSION`
- Added `prompt_version`/`schema_version` fields to provider meta on:
  - success
  - missing config
  - error/noop fallback
- Included version tags in chat system prompt text for traceability.

### 2) Event logging payload extension

File:
- `graphs/nodes/decide_trade.py`

Changes:
- Added `prompt_version` and `schema_version` to `strategist_llm/result` payload.
- Source priority:
  - provider `decision.meta`
  - strategist instance attributes

### 3) Ops script visibility extension

Files:
- `scripts/smoke_m20_llm.py`
- `scripts/query_strategist_llm_events.py`

Changes:
- smoke output now includes:
  - `prompt_version`
  - `schema_version`
- query human output now prints:
  - `prompt_version=...`
  - `schema_version=...`

### 4) Metrics report extension

File:
- `scripts/generate_metrics_report.py`

Changes:
- Added strategist LLM aggregate keys:
  - `prompt_version_total`
  - `schema_version_total`
- Added markdown sections:
  - Prompt Versions
  - Schema Versions

## Test Coverage

Updated files:
- `tests/test_m20_1_openai_provider_smoke.py`
- `tests/test_m20_3_llm_event_logging.py`
- `tests/test_m20_4_llm_ops_scripts.py`
- `tests/test_generate_metrics_report.py`

Validation command:
- `.\venv\Scripts\python.exe -m pytest -q tests/test_m20_1_openai_provider_smoke.py tests/test_m20_2_decide_trade_llm_flow.py tests/test_m20_3_llm_event_logging.py tests/test_m20_3_legacy_llm_router_compat.py tests/test_m20_4_llm_ops_scripts.py tests/test_generate_metrics_report.py`

Result:
- `25 passed`

## Safety Notes

- No execution or guard precedence behavior changed.
- Scope is LLM observability/metrics only.
