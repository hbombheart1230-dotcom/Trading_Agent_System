# 2026-05-24 Preopen Carry Guard

## Context

2026-05-22 ended with residual positions in local/account-synced state:

- `000660` qty 1
- `036540` qty 286

These positions were not intended weekend carries. The 2026-05-26 preopen priority is to confirm broker balance and flatten residual carry before allowing new entries.

## Patch

- Monitor entry guard now blocks new BUY intents when an open position has been carried for at least 12 hours.
- The block reason is `overnight_carry_recovery_pending`.
- Existing closeout unresolved markers still block with `closeout_unresolved_flatten_required`.
- SELL/exit logic is not blocked by this entry guard.

## 2026-05-26 Preopen Checklist

1. Sync Kiwoom portfolio balance.
2. Confirm whether `000660` and `036540` are still held.
3. If held, keep new BUY blocked and prioritize flatten/recovery handling.
4. Confirm monitor output surfaces `overnight_carry_recovery_pending` until residual carry is cleared.
5. After positions are flat, allow normal Q8 observation collection.

## Validation

- `tests/test_monitor_exit_guard.py::test_monitor_blocks_new_buy_when_overnight_carry_recovery_pending`
- `tests/test_monitor_exit_guard.py::test_monitor_eod_flat_overrides_pending_exit_lock`
