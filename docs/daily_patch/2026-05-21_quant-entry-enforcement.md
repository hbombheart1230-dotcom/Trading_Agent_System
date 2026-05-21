# 2026-05-21 Quant Entry Enforcement

## Purpose

Promote a small, high-confidence subset of Q1-Q7 quant diagnostics from
observation-only to live entry guard enforcement.

## Applied Behavior

`entry_quant_decision` remains a diagnostic object. A new enforcement adapter
reads it and blocks BUY only when the configured hard blockers are present.
The live monitor applies this only when the entry signal is already triggered
and no existing entry guard has already blocked the trade, so existing reasons
such as `minute_candle_missing` or `cost_adjusted_edge_not_ready` are preserved.

Default enforced blockers:

- `cost_edge_fail`
- `same_symbol_position_open`
- `directional_edge_evidence_missing`
- `volume_confirmation_missing`

Not enforced yet:

- `pullback_not_mature`
- `weak_tactic_suitability`
- scanner rank replacement
- post-exit-shadow hold extension
- long-horizon unlock

## Runtime Switches

- `QUANT_ENTRY_DECISION_MODE=enforce` enables the guard. This is the default.
- `QUANT_ENTRY_DECISION_MODE=observe` records the enforcement result without
  blocking.
- `QUANT_ENTRY_DECISION_MODE=advisory` records warnings without blocking.
- `QUANT_ENTRY_ENFORCED_BLOCKERS` can override the blocker list with a
  comma-separated list.

## Files

- `libs/runtime/quant/enforcement.py`
- `graphs/nodes/monitor_node.py`
- `tests/test_quant_decision.py`

## Verification

Focused regression:

- `tests/test_quant_decision.py`
- `tests/test_quant_context.py`
- `tests/test_strategist_frame_llm_integration.py`
- `tests/test_quant_tactic_report.py`
