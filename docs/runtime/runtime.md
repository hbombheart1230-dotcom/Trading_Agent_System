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

## Operational Visibility

- Runtime/agent visibility reference:
  - `docs/runtime/agent_visibility_runbook.md`
