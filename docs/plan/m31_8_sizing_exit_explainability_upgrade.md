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
  - `news_shock_threshold` + (`symbol_sentiment_score`, `global_sentiment_score`)
  - `emergency_halt`
  - `use_eod_flat` + `minutes_to_close` + `eod_flat_cutoff_min`
- existing stop-loss / take-profit / max-hold remain unchanged

## Strategy Sizing Context Wiring

Updated:

- `libs/strategies/contracts.py`
- `libs/strategies/v1/sizing_context.py` (new)
- `libs/strategies/v1/regime_momentum_v1.py`
- `libs/strategies/v1/mean_reversion_v1.py`
- `libs/strategies/v1/news_momentum_v1.py`
- `graphs/nodes/decide_trade.py`

Changes:

- added `StrategyInput.risk_context` as additive field
- `decide_trade` now passes runtime risk context into strategy-v1 input
- each strategy now forwards normalized sizing risk context into `evaluate_position_size`
- sizing now reflects runtime state (`degrade_mode`, exposure, volatility percentile, loss state) without breaking old contracts

## Decision Packet Explainability Wiring

Updated `graphs/nodes/decide_trade.py`:

- packet now consistently exposes additive explainability aliases:
  - `action`, `symbol`, `qty`
  - `why` (`regime` / `technical` / `news` / `policy`)
  - `invalidation`
  - `sizing_inputs` (when strategy-v1 decision exists)
- trace includes `why` and `invalidation` for operator diagnostics

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
  - news shock trigger
- `tests/test_strategy_v1_regime_momentum.py`
  - strategy-v1 sizing uses risk-context inputs
  - decision packet explainability fields present on strategy-v1 path
- `tests/test_m20_2_decide_trade_llm_flow.py`
  - exit policy `news_shock` integration in live decision flow
