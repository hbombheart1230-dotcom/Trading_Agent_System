# M31-8 Sizing and Exit Policy Upgrade

- Date: 2026-03-07
- Goal: make sizing and exits strategy-aware while preserving deterministic safety behavior.

## Position Sizing

Updated `libs/runtime/position_sizing.py`:

- added optional strategy-aware context inputs:
  - `regime`
  - `volatility_percentile`
  - `portfolio_exposure`
  - `correlation_bucket`
  - `daily_loss_state`
  - `degrade_mode`
- applies conservative multipliers to risk/notional budgets
- keeps backward compatibility with prior inputs/outputs

## Exit Policy

Updated `libs/runtime/exit_policy.py`:

- added optional exits:
  - `trailing_stop_pct` + `peak_price`
  - `vol_expansion_ratio` + (`current_volatility`, `baseline_volatility`)
  - `emergency_halt`
  - `use_eod_flat` + `minutes_to_close` + `eod_flat_cutoff_min`
- existing stop-loss / take-profit / max-hold remain unchanged

## Monitor Integration

Updated `graphs/nodes/monitor_node.py`:

- passes enriched risk context into position sizing
- forwards optional position/market context into exit policy evaluation
- captures extended exit diagnostics (`trailing_drawdown`, `volatility_ratio`, etc.)

## Tests

- `tests/test_strategy_sizing_exit_upgrade.py`
  - degrade-mode sizing contraction
  - trailing stop trigger
  - volatility expansion trigger
  - emergency halt / eod-flat trigger
