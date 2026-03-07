# M31-4 Strategy V1 Bootstrap

- Date: 2026-03-07
- Goal: keep safety-first runtime intact while introducing an explicit strategy module contract.

## Scope

1. Added strategy contracts in `libs/strategies/contracts.py`.
2. Added deterministic strategy config in `libs/strategies/v1/config.py`.
3. Added deterministic strategy implementation in `libs/strategies/v1/regime_momentum_v1.py`.
4. Integrated optional strategy path into `graphs/nodes/decide_trade.py` via `USE_STRATEGY_V1`.
5. Preserved existing approval/guard/execution flow (no bypass).

## Behavior

- When `USE_STRATEGY_V1=true` and no higher-priority static safety intent is active:
  - `RegimeMomentumV1` decides `BUY | SELL | NOOP`.
  - decision includes confidence, evidence, invalidation, and sizing inputs.
  - decision is mapped to existing intent contract (`ORDER_SUBMIT`, market order).
- Existing safety precedence remains:
  - cooldown / EOD liquidation / exit-policy static intents first.

## Env Additions

- `USE_STRATEGY_V1`
- `STRATEGY_V1_*` thresholds and sizing parameters (see `config/.env.example`)

## Tests

- `tests/test_strategy_v1_regime_momentum.py`
  - entry buy scenario
  - exit sell scenario
  - `decide_trade` integration with feature flag
