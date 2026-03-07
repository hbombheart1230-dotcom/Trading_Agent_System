# M31+ Runtime Safety Patch (2026-03-07)

- Date: 2026-03-07
- Goal: reduce blind-trading risk when broker portfolio snapshot fails and enforce deterministic pre-close liquidation.

## Changes

1. Portfolio snapshot health metadata added.
- File: `graphs/nodes/build_portfolio_snapshot.py`
- Added `_health` block into `portfolio_snapshot` and `state["portfolio_snapshot_health"]`.
- Includes: `reader_ok`, `reader_error`, `source`, `fallback_applied`, `kiwoom_mode`, `execution_mode`.

2. BUY guard on unhealthy portfolio snapshot (real execution path).
- File: `graphs/nodes/execute_from_packet.py`
- New guard blocks BUY with reason `portfolio_snapshot_reader_error` when snapshot health indicates reader failure.
- Controlled by env: `PORTFOLIO_SNAPSHOT_HEALTH_GUARD_ENABLED` (default `true`).

3. End-of-day forced liquidation intent.
- File: `graphs/nodes/decide_trade.py`
- New pre-close rule can emit `SELL` regardless of LLM/rule intent.
- Controlled by env:
  - `USE_EOD_FORCE_LIQUIDATION`
  - `EOD_FORCE_LIQUIDATION_START_HHMM`
  - `EOD_FORCE_LIQUIDATION_END_HHMM`

## Tests Added

- `tests/test_m9_snapshots.py`
  - health metadata presence
  - reader-error health flag in mock mode
- `tests/test_execute_from_packet.py`
  - BUY blocked when snapshot health is reader-error in real execution mode
- `tests/test_m20_2_decide_trade_llm_flow.py`
  - EOD force-liquidation emits SELL near market close window

## Operator Notes

1. If `portfolio_snapshot._health.reader_ok=false` appears repeatedly, treat account snapshot as degraded and investigate broker/account API before resuming normal BUY flow.
2. Enable `USE_EOD_FORCE_LIQUIDATION=true` for intraday same-day-flat policy sessions.
