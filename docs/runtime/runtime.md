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
   - `candidates` (Top-N)
   - `strategist_output`
2. Scanner consumes strategist candidates only and writes:
   - `scan_results`
   - `selected`
   - `top_stock`
   - `scanner_output`
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
