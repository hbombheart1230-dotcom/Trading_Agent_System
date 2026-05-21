# 2026-05-20 Quant Tactic Engine Q1

## Scope

Phase Q1 of `docs/tactics/quant_tactic_engine_phase_plan.md`.

This patch introduces the modular quant tactic contract/catalog layer without
changing live trading behavior.

## Changes

- Added `libs/runtime/quant/contracts.py`
  - tactic ID contract
  - legacy tactic aliases
  - pullback subtype contract
  - serializable `FactorSnapshot`, `TacticScorecard`, and `QuantDecision`
    dataclasses
- Added `libs/runtime/quant/tactics.py`
  - playbook to tactic default mapping
  - playbook to tactic candidate mapping
  - tactic runner-up rank defaults
  - alias-safe tactic and subtype normalization helpers
- Added `libs/runtime/quant/__init__.py`
- Updated `graphs/nodes/strategist_node.py`
  - moved tactic normalization and subtype normalization onto the new quant
    tactic catalog
  - preserved `leader_vwap_reclaim_pullback -> vwap_reclaim_pullback`
    behavior
  - preserved `theme_leader_pullback -> theme_confirmed_pullback` behavior
- Updated `libs/strategies/playbook_contracts.py`
  - exposes tactic IDs, legacy aliases, and default tactic mapping through
    `playbook_inventory()`
- Added `tests/test_quant_tactics.py`

## Behavior

No live behavior change intended.

The patch only centralizes the tactic vocabulary and normalization rules so
later factor, memory, scorecard, scanner, monitor, and report patches can call
one modular source instead of embedding tactic logic in large runtime files.

## Verification

Passed:

```powershell
venv\Scripts\python.exe -m pytest -q tests/test_quant_tactics.py tests/test_strategist_frame_llm_integration.py tests/test_canonical_artifact_validation.py
```

Result:

- 56 passed
