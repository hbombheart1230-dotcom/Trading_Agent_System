# M20-3: Legacy LLM Router Compatibility Fix

- Date: 2026-02-14
- Goal: restore backward compatibility for `libs.llm.router` while keeping newer role-based routing behavior.

## Problem

- `libs/llm/router.py` imports `ChatMessage` from `libs.llm.openrouter_client`.
- `ChatMessage` was missing in `openrouter_client.py`, causing legacy import/runtime failure:
  - `ImportError: cannot import name 'ChatMessage'`

## Implemented Changes

### 1) Restore legacy type export

File:
- `libs/llm/openrouter_client.py`

Change:
- Added backward-compatible alias:
  - `ChatMessage = Dict[str, Any]`

Effect:
- `libs.llm.router` import path works again.
- Legacy wrapper and newer `libs.llm.llm_router` can coexist.

### 2) Add regression tests for legacy path

File:
- `tests/test_m20_3_legacy_llm_router_compat.py`

Coverage:
- validates legacy import path (`LLMRouter`, `TextLLMRouter`, `ChatMessage`)
- validates legacy router `chat()` payload build/forward behavior

## Validation Result

- Command:
  - `.\venv\Scripts\python.exe -m pytest -q tests/test_m20_3_legacy_llm_router_compat.py tests/test_m20_1_openai_provider_smoke.py tests/test_m20_2_decide_trade_llm_flow.py tests/test_m20_3_llm_event_logging.py`
- Result:
  - `16 passed`

## Safety Notes

- No execution path or guard precedence changed.
- Scope is limited to LLM router compatibility and documentation/tests.
