# M31-17 Strategist Theme/Candidate Flow Upgrade

- Date: 2026-03-10
- Scope: additive contract update for Strategist -> Scanner -> Monitor chain.

## Objective

Align runtime outputs with operator-facing architecture:

1. Strategist emits `themes` and Top-N `candidates`.
2. Scanner evaluates strategist candidates only and exposes `top_stock`.
3. Monitor remains entry/exit-only and keeps execution separation unchanged.

## Code Changes

- `graphs/nodes/strategist_node.py`
  - Added Top-N resolution via `TOP_N_CANDIDATES` fallback.
  - Added additive outputs:
    - `state["themes"]`
    - `state["candidate_symbols"]`
    - `state["strategist_output"]`

- `graphs/nodes/scanner_node.py`
  - Reads candidates from `strategist_output.candidates` when `state["candidates"]` is absent.
  - Added additive outputs:
    - `state["top_stock"]`
    - `state["scanner_output"]`

- `graphs/nodes/scan_candidates.py`
  - Added strategist-output candidate injection priority for compatibility paths.

- `graphs/nodes/monitor_node.py`
  - Added `SELL_COOLDOWN` env alias support (`SELL_COOLDOWN_SEC` remains valid).
  - Added open-order pending sell guard (`sell_guard_open_order_pending`).
  - Added additive `state["monitor_output"]`.

- `graphs/nodes/decide_trade.py`
  - Added `SELL_COOLDOWN` env alias support.

## Documentation Sync

- `README.md`
- `docs/architecture/architecture.md`
- `docs/architecture/system_flow.md`
- `docs/runtime/runtime.md`
- `docs/agents.md`
- `docs/io_contracts.md`
- `docs/dtos.md`
- `docs/en/05_runtime_flow.md`
- `docs/ko/05_runtime_flow.md`
- `docs/en/13_project_tree.md`
- `docs/ko/13_project_tree.md`

## Migration Notes

- Backward compatibility is preserved:
  - Existing `state["candidates"]` and `state["selected"]` contracts still work.
  - Existing `SELL_COOLDOWN_SEC` remains supported.
- New optional env key:
  - `TOP_N_CANDIDATES` (default 5)
- Sell timing guards now accept either:
  - `SELL_COOLDOWN`
  - `SELL_COOLDOWN_SEC`
