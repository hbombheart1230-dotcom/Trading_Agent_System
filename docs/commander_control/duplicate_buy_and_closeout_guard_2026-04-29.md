# Duplicate Buy And Closeout Guard - 2026-04-29

## Background

On 2026-04-28, `005380` received repeated late-session BUY orders before the portfolio snapshot reflected the newly accepted order. The closeout guard also trusted a stale `market_context.minutes_to_close` value, so the system did not recognize that the session was already near the close.

## Guard Rules

- Commander and monitor recompute `minutes_to_close` from the runtime KST clock when `tick_ts` or another reliable runtime clock is present.
- If an existing `market_context.minutes_to_close` differs from the runtime value by more than one minute, runtime clock wins.
- The previous closeout value/source is kept in `market_clock_previous_minutes_to_close` and `market_clock_previous_source`.
- Fresh BUY blocking uses a separate entry-side closeout buffer: `monitor.entry.buy_closeout_cutoff_min`.
- The default entry-side closeout buffer is 15 minutes and is never smaller than `monitor.exit.eod_flat.cutoff_min`.
- `monitor.exit.eod_flat.cutoff_min` keeps its original meaning as the EOD flatten/held-position cutoff.
- Executor rechecks the same BUY closeout guard before order submission so stale monitor output cannot submit a late BUY.
- Execution records successful same-symbol BUY orders in `data/state/execution_recent_buy_guard.json`.
- A same-symbol BUY is blocked while the recent BUY record is still active, even if the portfolio snapshot has not yet reflected the position.
- A successful SELL clears that symbol's recent BUY record.
- During the session closeout fast-path, Commander checks account orders for pending BUY rows and submits a `kt10003` CANCEL intent before running monitor closeout logic.

## 2026-05-04 Follow-Up

`036540` received a BUY at 15:21 and filled at 15:30:29. This was not an intentional overnight carry. The monitor treated `minutes_to_close=10.4667` as outside the 10-minute EOD cutoff, but the accepted order did not become a reflected position until after the closeout path had already evaluated holdings.

The fix separates the two concepts:

- New entries are blocked from 15 minutes before close by default.
- Existing positions are still flattened by the EOD cutoff policy.
- Pending BUY orders are cancelled first when the closeout fast-path activates.

## Scope

This is a safety/idempotency guard, not a strategy-threshold relaxation.

- It does not force a HOLD.
- It does not lower entry thresholds.
- It does not override monitor entry logic.
- It prevents duplicate exposure caused by broker/account reflection lag.

## Validation

Covered by:

- `tests/test_execute_from_packet.py::test_execute_from_packet_blocks_recent_same_symbol_buy_before_position_reflects`
- `tests/test_execute_from_packet.py::test_execute_from_packet_blocks_new_buy_inside_entry_closeout_buffer`
- `tests/test_m21_commander_runtime_entry.py::test_m21_session_closeout_fast_path_uses_buy_buffer_before_eod_cutoff`
- `tests/test_m21_commander_runtime_entry.py::test_m21_integrated_chain_closeout_cancels_pending_buy_before_monitor`
- `tests/test_m21_commander_runtime_entry.py::test_m21_ensure_market_context_clock_fields_overrides_stale_minutes_to_close_from_tick_ts`
- `tests/test_monitor_exit_guard.py::test_monitor_blocks_new_buy_inside_entry_closeout_buffer`
- `tests/test_monitor_exit_guard.py::test_monitor_overrides_stale_minutes_to_close_before_entry_closeout_guard`

Live restart on 2026-04-29 loaded the patched runtime. The account state immediately after restart was flat (`open_positions=0`) and the next cycles were blocked by post-exit cooldown rather than repeated BUY. A later accepted BUY for `098460` was recorded in the recent BUY guard, and the following watch cycle did not add another BUY.
