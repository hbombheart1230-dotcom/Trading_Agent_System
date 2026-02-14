# M20-2: OpenRouter Adapter + Schema Normalization + Retry/Telemetry

- Date: 2026-02-14
- Goal: Keep strategist LLM integration robust on OpenRouter while preserving strict safe-failure behavior.

## Scope

1. Parse OpenRouter chat-completions responses without changing OpenRouter endpoint usage.
2. Normalize strategist output to canonical intent schema before decision packet handoff.
3. Add retry/backoff for transient transport failures.
4. Add strategist LLM telemetry in event logs for operator visibility.

## Implemented Changes

### 1) OpenRouter adapter parsing in strategist provider

File:
- `libs/ai/providers/openai_provider.py`

Changes:
- Kept OpenRouter default chat-completions endpoint contract.
- Added assistant content parsing path:
  - extract `choices[0].message.content`
  - strip fenced code blocks
  - extract first JSON object from free text
- Adapted parsed JSON into canonical strategist return shape:
  - accepts `{"intent": {...}}` and direct `{"action": ...}` style payloads
- Preserved safe failure:
  - unparsable content returns NOOP (`reason=strategist_error`) without raising upstream.

### 2) Intent schema normalization before output

File:
- `libs/ai/providers/openai_provider.py`

Changes:
- Added explicit canonicalization via `normalize_intent(...)`.
- Filled defaults from runtime context (`symbol`, `price`) when missing.
- Ensured normalized output remains compatible with downstream execution guards.

### 3) Retry/backoff policy for transient failures

File:
- `libs/ai/providers/openai_provider.py`

Changes:
- Added configurable retry policy:
  - `AI_STRATEGIST_RETRY_MAX`
  - `AI_STRATEGIST_RETRY_BACKOFF_SEC`
- Implemented exponential backoff for retryable errors (timeout/network/5xx/429 family).
- Attached `attempts` metadata to strategist response for observability.

### 4) Strategist LLM event telemetry

File:
- `graphs/nodes/decide_trade.py`

Changes:
- Added dedicated event log stage:
  - `stage="strategist_llm"`
  - `event="result"`
- Logged key payload fields:
  - `ok`, `latency_ms`, `intent_action`, `intent_reason`
  - `attempts`, `endpoint_type`, `error_type`
  - `provider`, `model`, `endpoint` (when available)
- Kept behavior-only logging:
  - telemetry is observational and does not alter decision/execution flow.

## Test Coverage

- `tests/test_m20_1_openai_provider_smoke.py`
  - env parsing, OpenRouter content adaptation, retry/backoff, normalization, safe NOOP cases
- `tests/test_m20_2_decide_trade_llm_flow.py`
  - decide_trade OpenAI success/noop/fallback behavior
- `tests/test_m20_3_llm_event_logging.py`
  - strategist telemetry on success and failure

## Validation Result

- Command:
  - `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_m20_1_openai_provider_smoke.py tests/test_m20_2_decide_trade_llm_flow.py tests/test_m20_3_llm_event_logging.py`
- Result:
  - `14 passed`

## Safety Notes

- No execution guard precedence changed.
- No approval bypass introduced.
- LLM failures remain safe NOOP by default.

## Next

1. Add operator-facing smoke script options for explicit retry visibility.
2. Add dashboard/query snippets for `strategist_llm` telemetry fields.
