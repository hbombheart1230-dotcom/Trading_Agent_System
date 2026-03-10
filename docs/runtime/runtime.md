# Runtime Model

## TradeState (single source of truth)
- mode (mock/real)
- account snapshot
- positions + open orders
- current run_config / strategist_output / scan_result
- watchlist + latest signals

## EventLog (append-only)
- agent outputs
- skill calls + results
- approvals (audit)
- errors

**Goal:** make every run replayable.

## Runtime Decision Chain (Current)

1. Strategist writes:
   - `themes`
   - `candidates` (Top-N, optional hint)
   - `strategist_output`
2. Scanner uses Kiwoom market data as primary candidate source and writes:
   - `scanner_candidate_pool` (source, counts, theme-filter metadata)
   - `scan_results`
   - `selected`
   - `top_stock`
   - `scanner_output`
   - Candidate flow:
     - top volume/value/change-rate + condition search
     - optional theme/sector filter with `theme_map` / `sector_map`
     - strategist candidate fallback when Kiwoom pool is empty
3. Monitor handles entry/exit only and writes:
   - `intents`
   - `monitor_exit`
   - `monitor_output`
4. Supervisor/Executor remain the only approval/execution path.

## M13 Tick Pipeline Selection

- `scripts/run_m13_live_loop.py` supports two tick paths:
  - `legacy_m10` (default): `m13_tick -> m10_live_pipeline -> decide_trade -> execute_from_packet`
  - `integrated_chain`: `m13_tick -> commander_runtime(mode=integrated_chain)`
- Control knobs:
  - CLI: `--tick-pipeline legacy_m10|integrated_chain`
  - ENV: `M13_TICK_PIPELINE`
- Symbol requirement:
  - `legacy_m10` requires `symbol`
  - `integrated_chain` can run without a preselected symbol

## Operational Visibility

- Runtime/agent visibility reference:
  - `docs/runtime/agent_visibility_runbook.md`
