# M31-12 Strategy V1 Multi-Strategy Registry

- Date: 2026-03-07
- Goal: extend `strategy_v1` from single implementation (`RegimeMomentumV1`) to selectable multi-strategy without breaking existing decision/execution contracts.

## What Changed

1. Added new deterministic strategy modules
- `libs/strategies/v1/mean_reversion_v1.py`
- `libs/strategies/v1/news_momentum_v1.py`

2. Added strategy config scaffolds
- `libs/strategies/v1/config.py`
  - `MeanReversionV1Config` + loader
  - `NewsMomentumV1Config` + loader

3. Added strategy registry/selector
- `libs/strategies/v1/registry.py`
  - `resolve_strategy_v1_name(policy, llm_context)`
  - `select_auto_strategy_v1(llm_context)`
  - `build_strategy_v1(name, policy)`

4. Wired strategy registry into decision path
- `graphs/nodes/decide_trade.py`
  - keeps `USE_STRATEGY_V1` gate behavior
  - new selector input: `policy.strategy_v1_name` or env `STRATEGY_V1_NAME`
  - supported: `regime_momentum_v1 | mean_reversion_v1 | news_momentum_v1 | auto`
  - writes `state["strategy_v1_name"]` and `decision_trace["strategy_v1_name"]`

5. Expanded exports
- `libs/strategies/v1/__init__.py`

## Compatibility

- Existing default behavior preserved:
  - if strategy v1 is enabled and no strategy name is set, it still uses `RegimeMomentumV1`.
- Existing decision packet contract is unchanged:
  - `decision_packet.intent` remains `BUY|SELL|NOOP` + existing fields.
- Existing safety flow is unchanged:
  - approval/guard precedence/execution gating remains intact.

## Tests

- Added:
  - `tests/test_strategy_v1_multi_strategy_selection.py`
    - mean reversion direct decision test
    - news momentum status gating test
    - `decide_trade` strategy selection test (`news_momentum_v1`)
    - `decide_trade` auto selection test (`mean_reversion_v1`)

- Regression:
  - full suite pass: `497 passed`
