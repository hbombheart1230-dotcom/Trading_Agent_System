# M31-17 Strategist Theme/Candidate Flow Upgrade

- Date: 2026-03-10
- Scope: additive contract update for Strategist -> Scanner -> Monitor chain.

## Objective

Align runtime outputs with operator-facing architecture.

Note (2026-03-10 update):
- Scanner candidate acquisition is now Kiwoom-market-data-first.
- Strategist candidates remain optional hints/fallback only.
- Scanner scoring now returns explainable `score_breakdown` and `ranked_candidates`.

1. Strategist emits `themes` and Top-N `candidates`.
2. Scanner builds/ranks Kiwoom candidate pool (with theme filter) and exposes `top_stock`.
3. Monitor remains entry/exit-only and keeps execution separation unchanged.

## Code Changes

- `graphs/nodes/strategist_node.py`
  - Added Top-N resolution via `TOP_N_CANDIDATES` fallback.
  - Added additive outputs:
    - `state["themes"]`
    - `state["candidate_symbols"]`
    - `state["strategist_output"]`

- `graphs/nodes/scanner_node.py`
  - Uses Kiwoom candidate provider by default.
  - Candidate sources:
    - top trading value / top volume / top gainers
    - condition search
    - sector/theme mapped symbols
    - operator watchlist shortlist
  - Applies practical pool reduction (halt/abnormal/illiquid filters).
  - Applies theme/sector filtering via `theme_map` / `sector_map`.
  - Reads candidates from `strategist_output.candidates` as fallback when Kiwoom pool is empty.
  - Added additive outputs:
    - `state["top_stock"]`
    - `state["scanner_output"]`
    - `state["ranked_candidates"]`
    - `state["scanner_candidate_pool"]` (reduction metadata included)

- `graphs/nodes/scan_candidates.py`
  - Added Kiwoom candidate source path (`CANDIDATE_SOURCE=kiwoom` default).
  - Keeps strategist-output candidate injection as compatibility fallback.

- `graphs/nodes/monitor_node.py`
  - Added `SELL_COOLDOWN` env alias support (`SELL_COOLDOWN_SEC` remains valid).
  - Added monitor-side sell stabilization guards:
    - `MIN_HOLD_SECONDS` (normal exit hold guard)
    - `SELL_COOLDOWN`/`SELL_COOLDOWN_SEC` (post-sell suppression window)
    - `MONITOR_EXIT_CONFIRM_TICKS` (consecutive confirmation)
  - Added duplicate SELL suppression maps:
    - `_monitor_pending_exit_lock`
    - `_monitor_sell_cooldown_until`
    - `_monitor_prev_position_qty`
  - Added explicit emergency exit tagging (`emergency_halt`, `news_shock`) separate from normal confirmation path.
  - Expanded monitor observability payload (`monitor_reason`, guard-block flags, confirmation/cooldown fields).
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
