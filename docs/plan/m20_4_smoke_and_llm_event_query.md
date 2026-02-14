# M20-4: Operator Smoke Visibility + Strategist LLM Event Query

- Date: 2026-02-14
- Goal: make strategist LLM smoke runs easier to inspect and add a lightweight ops query CLI for `strategist_llm` telemetry.

## Scope

1. Extend smoke CLI to expose run-level LLM event details (attempts/latency/error).
2. Add standalone log query script for strategist LLM result events.
3. Add regression tests and roadmap/docs updates.

## Implemented Changes

### 1) Smoke script output enhancement

File:
- `scripts/smoke_m20_llm.py`

Changes:
- Added options:
  - `--event-log-path` (override `EVENT_LOG_PATH`)
  - `--show-llm-event` (print latest `strategist_llm/result` summary for current `run_id`)
  - `--require-llm-event` (exit with code `3` if event missing)
- Added event summary fields in output:
  - `ok`, `provider`, `model`, `latency_ms`, `attempts`, `intent_action`, `intent_reason`, `error_type`
- Existing safety semantics preserved:
  - no execution path invoked from smoke script

### 2) Strategist LLM event query CLI

File:
- `scripts/query_strategist_llm_events.py`

Features:
- Reads JSONL event log (`EVENT_LOG_PATH` by default)
- Filters only `stage="strategist_llm"` + `event="result"`
- Supports:
  - `--run-id`
  - `--only-failures`
  - `--limit`
  - `--json`
- Returns non-zero (`2`) when path does not exist

## Tests

File:
- `tests/test_m20_4_llm_ops_scripts.py`

Coverage:
- smoke script prints llm event summary in openai mode
- smoke script `--require-llm-event` failure path
- query script failure-only JSON filter
- query script missing path error code

## Validation Result

- Command:
  - `.\venv\Scripts\python.exe -m pytest -q tests/test_m20_4_llm_ops_scripts.py tests/test_smoke_m20_llm_script.py tests/test_m20_1_openai_provider_smoke.py tests/test_m20_2_decide_trade_llm_flow.py tests/test_m20_3_llm_event_logging.py tests/test_m20_3_legacy_llm_router_compat.py`
- Result:
  - `22 passed`

## Safety Notes

- Execution guards and approval chain are unchanged.
- New scripts are read/inspect helpers and do not place orders.
