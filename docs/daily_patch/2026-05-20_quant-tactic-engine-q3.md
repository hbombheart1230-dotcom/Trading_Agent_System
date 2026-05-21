# 2026-05-20 Quant Tactic Engine Q3

## Scope

Phase Q3 of `docs/tactics/quant_tactic_engine_phase_plan.md`.

This patch adds memory and scorecard adapters for the quant tactic layer. It
does not change live trading behavior.

## Changes

- Added `libs/runtime/quant/memory.py`
  - loads operator daily/weekly/monthly summary JSON
  - converts `pattern_performance` into a compact `quant_memory_packet.v1`
  - extracts tactic, playbook, horizon, scanner rank, entry, exit, cost floor,
    and combined rows
- Added `libs/runtime/quant/scorecard.py`
  - converts quant memory packet into `quant_scorecard.v1`
  - emits tactic-level scorecards
  - detects loss clusters from exit reason performance
  - exposes compact LLM-ready scorecard
- Added `tests/test_quant_memory_scorecard.py`

## Behavior

No live behavior change intended.

All scorecard outputs carry:

- `behavior_effect=observation_only`

## Verification

Passed:

```powershell
venv\Scripts\python.exe -m pytest -q tests/test_quant_memory_scorecard.py tests/test_quant_factors.py tests/test_quant_tactics.py
```

Result:

- 9 passed

Additional related checks passed:

```powershell
venv\Scripts\python.exe -m pytest -q tests/test_strategist_frame_llm_integration.py tests/test_operator_summary_reports.py
venv\Scripts\python.exe -m pytest -q tests/test_m21_commander_runtime_entry.py
```

Result:

- 57 passed
- 83 passed
