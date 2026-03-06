# Runtime Model

## TradeState (single source of truth)
- mode (mock/real)
- account snapshot
- positions + open orders
- current run_config / trade_plan / scan_result
- watchlist + latest signals

## EventLog (append-only)
- agent outputs
- skill calls + results
- approvals (audit)
- errors

**Goal:** make every run replayable.

## Operational Visibility

- Runtime/agent visibility reference:
  - `docs/runtime/agent_visibility_runbook.md`
