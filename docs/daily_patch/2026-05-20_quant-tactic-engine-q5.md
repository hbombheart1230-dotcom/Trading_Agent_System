# 2026-05-20 Quant Tactic Engine Q5

## Scope

Phase Q5 adds scanner-side tactic suitability as an observation-only diagnostic
layer.

The purpose is to show whether a scanner candidate is ranked highly because it
actually fits the current tactic, or because it is simply liquid, high rank, or
large-cap representative.

## Changes

- Added `libs/runtime/quant/suitability.py`.
- Added tactic-specific suitability scoring for:
  - `vwap_reclaim_pullback`
  - `lower_vwap_rebound_probe`
  - breakout and momentum tactics
  - reversal and mean-reversion probes
  - defensive fallback cases
- Attached `tactic_suitability` to scanner candidate rows.
- Exposed `tactic_suitability` through:
  - selected scanner output
  - scanner ranking table rows
  - scanner candidate selection reason payload
  - compact selected scanner snapshot
- Preserved live behavior:
  - no ranking replacement
  - no symbol-name penalty
  - no entry/exit rule change
  - `behavior_effect=observation_only`

## Operator Impact

Scanner review can now distinguish these cases:

- high rank because liquidity and trading value are strong
- high rank because the symbol fits the strategist tactic
- weak tactic fit with missing VWAP, volume, cost, or chart evidence

This is intended to make Samsung Electronics, SK Hynix, ETF/inverse, and
runner-up selection reviews easier without hard-coding symbol penalties.

## Validation

Passed:

```text
venv\Scripts\python.exe -m pytest -q tests/test_quant_suitability.py tests/test_quant_factors.py tests/test_scanner_strategy_frame_integration.py tests/test_monitor_candidate_cascade.py
27 passed

venv\Scripts\python.exe -m pytest -q tests/test_m21_commander_runtime_entry.py
83 passed

venv\Scripts\python.exe -m pytest -q tests/test_quant_context.py tests/test_strategist_frame_llm_integration.py
43 passed
```

## Restart

No restart was performed for this refactor slice.

Live behavior remains unchanged unless the running process is restarted with the
new code.

## Follow-Up

Next phase is Q6: monitor-side observation decision.

Q6 should add tactic-aware entry/exit diagnostics and expected hold-window
comparison without immediately changing live entry/exit behavior.
