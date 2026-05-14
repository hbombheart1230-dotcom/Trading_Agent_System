# 2026-05-12 Defensive top3 and repeat loss guard

## Issue

- `RISK_MAX_POSITIONS=3` was active, but after a risk-off/defensive turn the commander accepted a strategist watch policy that narrowed monitoring to rank 1 only.
- This caused no-trade gaps even when `capacity_remaining=3`.
- Same-day repeat losers, especially `003060`, were only weakly penalized by scanner symbol prior logic and could keep returning through runner-up cascade.

## Patch

- In defensive/risk-off mode, repeated expandable blockers such as `below_vwap_reclaim_not_ready` can now reopen a conservative top3 cascade when there is position capacity.
- This keeps the system defensive, but avoids the single-candidate deadlock.
- Scanner symbol prior now applies a strong same-day repeat-loss penalty when a symbol has multiple closed losses or clearly negative same-day average return.
- The penalty increases risk, lowers confidence, and records `same_day_repeat_loss` / `same_day_trade_lockout_bias` in the symbol prior reasons.

## Expected Effect

- Position capacity of 3 can actually matter during defensive no-trade streaks.
- Repeated failed symbols should fall materially in scanner ranking instead of staying viable through theme/volume boosts.
- The system still requires monitor confirmation and cost-aware entry evidence before buying.

## Verification

- `python -m pytest -q tests/test_monitor_feedback_adaptive_policy.py tests/test_scanner_strategy_frame_integration.py`
- Result: `22 passed`
- `py_compile` passed for:
  - `graphs/commander_runtime.py`
  - `graphs/nodes/scanner_node.py`
