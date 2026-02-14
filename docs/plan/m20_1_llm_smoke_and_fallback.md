# M20-1: LLM Strategist Smoke + Safe Fallback Hardening

- Date: 2026-02-14
- Goal: Validate that the LLM strategist path is alive, deterministic enough for CI, and always safe on failure.

## Scope

1. Provider-level smoke hardening (`OpenAIStrategist`)
2. `decide_trade` integration smoke (LLM success + failure safety)
3. Operator smoke script (no execution path)
4. Tests for timeout / invalid response shape / fallback

## Implemented Changes

### 1) Provider hardening

File:
- `libs/ai/providers/openai_provider.py`

Changes:
- Added optional `max_tokens` on strategist construction and env parsing:
  - `AI_STRATEGIST_MAX_TOKENS`
- Added missing-config guard in `decide()`:
  - if `api_key` or `endpoint` is missing -> safe NOOP (`reason=missing_config`)
- Added response schema guard:
  - if `resp["intent"]` is not an object/dict -> treat as error and return safe NOOP
- Preserved strict safety behavior:
  - provider errors/timeouts never raise to caller; return NOOP with `reason=strategist_error`

### 2) Integration smoke path in decision node

Target path:
- `graphs/nodes/decide_trade.py`

Validated behavior:
- OpenAI strategist success -> normalized BUY/SELL/NOOP intent flows into `decision_packet`
- OpenAI strategist timeout/error -> safe NOOP (no execution side effect)
- Non-openai injected strategist exception -> RuleStrategist fallback

### 3) CLI smoke script

File:
- `scripts/smoke_m20_llm.py`

Purpose:
- Run strategist + `decide_trade` only.
- Never calls execution pipeline.

Key options:
- `--provider openai|rule`
- `--require-openai` (fails if routed strategist is not `OpenAIStrategist`)
- `--symbol`, `--price`, `--cash`, `--open-positions`

Example:

```powershell
.\venv\Scripts\python.exe scripts\smoke_m20_llm.py --provider openai --require-openai
```

## Test Coverage Added

### Provider smoke tests
- `tests/test_m20_1_openai_provider_smoke.py`
  - env parsing (`timeout`, `max_tokens`)
  - successful POST payload/response parse
  - timeout -> safe NOOP
  - invalid intent shape -> safe NOOP
  - missing config -> safe NOOP

### `decide_trade` flow tests
- `tests/test_m20_2_decide_trade_llm_flow.py`
  - OpenAI success path
  - OpenAI timeout safe NOOP path
  - non-openai broken strategist -> Rule fallback

### Smoke script tests
- `tests/test_smoke_m20_llm_script.py`
  - rule mode returns success
  - `--require-openai` fails correctly when not openai

## Validation Result

- M20-related test set: `13 passed`
- Full suite regression: `122 passed`

## Safety Notes

- This milestone does **not** change execution guards.
- This milestone does **not** enable order execution from smoke script.
- Decision and execution remain separated by design.

## Next (M20-2 candidate)

1. Add structured prompt contract (strict schema response)
2. Add retry/backoff policy for transient LLM transport errors
3. Add LLM call telemetry fields (`latency`, `error_type`, `provider`) to event logs
