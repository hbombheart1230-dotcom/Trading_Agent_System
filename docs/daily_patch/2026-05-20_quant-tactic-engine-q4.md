# 2026-05-20 Quant Tactic Engine Q4

## Scope

Phase Q4 of `docs/tactics/quant_tactic_engine_phase_plan.md`.

This patch injects compact quant context into strategist LLM payloads. It does
not change scanner ranking, monitor entry/exit, execution, or live behavior.

## Changes

- Added `libs/runtime/quant/context.py`
  - resolves trading day and weekly period key
  - loads quant memory packet and scorecard
  - builds `strategist_quant_context.v1`
  - builds stage-specific context for selected-symbol, hold, and carry reviews
- Updated `graphs/nodes/strategist_node.py`
  - adds `reports_root` to LLM payload in runtime calls
  - injects `quant_context` into compact strategist payload
  - instructs strategist LLM to use quant context as deterministic
    observation-only evidence
  - keeps direct test payloads without explicit `reports_root` from loading
    repo-local weekly summaries by accident
- Added `tests/test_quant_context.py`
- Extended strategist LLM integration tests to assert Stage 3/4 quant context
  presence.

## Stage Context

Stage 1 market frame:

- `quant_market_context`
- compact weekly tactic scorecard
- loss clusters
- cost-floor rows

Stage 2 selected-symbol tactical refresh:

- `selected_symbol_quant_snapshot`
- sourced from scanner candidate `quant_factor_snapshot` when available

Stage 3 stale intraday hold review:

- `hold_quant_context`
- current position, monitor reason, active exit axis, entry factor snapshot

Stage 4 end-of-day carry review:

- `carry_quant_context`
- selected/current position, open positions, post-exit shadow placeholder

## Behavior

No live behavior change intended.

All context carries:

- `behavior_effect=observation_only`

## Verification

Passed:

```powershell
venv\Scripts\python.exe -m pytest -q tests/test_quant_context.py tests/test_quant_memory_scorecard.py tests/test_quant_factors.py tests/test_quant_tactics.py tests/test_strategist_frame_llm_integration.py
venv\Scripts\python.exe -m pytest -q tests/test_m21_commander_runtime_entry.py
venv\Scripts\python.exe -m pytest -q tests/test_operator_summary_reports.py tests/test_scanner_strategy_frame_integration.py
```

Result:

- 52 passed
- 83 passed
- 30 passed
