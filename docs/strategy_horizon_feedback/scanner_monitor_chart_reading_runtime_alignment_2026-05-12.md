# Scanner and Monitor Chart Reading Runtime Alignment - 2026-05-12

## Decision

Keep the strategist flow as the strategy authority. Do not add a new strategist schema yet.

Use existing strategist output fields to steer the downstream engines:

- `playbook`
- `scanner_priority`
- `risk_tone`
- `trade_aggressiveness`
- `monitor_entry_policy`
- `strategy_horizon`

The scanner and monitor should not invent a different strategy. They should calculate whether the current candidate and current price action fit the strategy frame.

## Scanner Role

Scanner is the bigger-picture candidate ranker.

It should evaluate:

- daily or longer OHLCV-derived features when available
- MA20/MA60/MA120 alignment
- ADX/trend strength
- 20-period return and drawdown
- relative strength and cross-section rank
- volume accumulation or volume spike
- breakout/base quality
- volatility, gap, and overextension risk

The runtime field for this is:

```text
scanner_macro_chart_fit
```

Authority:

```text
soft_rank_bias_only
```

Meaning:

- It can mildly change candidate order.
- It cannot directly create an order.
- It cannot bypass monitor entry gating.
- It stays neutral when feature coverage is insufficient.

## Monitor Role

Monitor is the live timing engine.

It should evaluate:

- short-window candles
- VWAP hold/reclaim quality
- breakout and pullback readiness
- volume confirmation
- extension from VWAP
- last candle quality
- reward-room quality
- multi-window short-term structure
- cost-aware edge and exit risk

The new monitor detail field is:

```text
human_chart_detail_context
```

It feeds the existing `human_chart_entry_setup` positive entry path. A near-ready setup can be promoted from WAIT to BUY only when the chart context is clean and the final candle/reward-risk context is not weak.

## Strategist Integration

No new LLM field is required for this patch.

Current mapping:

- `playbook=breakout`: scanner macro chart-fit weights breakout/base, volume accumulation, and relative strength slightly higher.
- `playbook=pullback|reversal`: scanner macro chart-fit weights trend alignment and risk balance slightly higher.
- `playbook=defensive`: scanner macro chart-fit weights risk balance higher.
- `risk_tone=conservative`: scanner macro chart-fit gives more weight to risk balance.
- `trade_aggressiveness=high`: scanner macro chart-fit gives more weight to relative strength and breakout/base.
- `scanner_priority`: keyword-level hints can tilt trend, relative strength, ADX, volume, breakout, or risk balance.

## Report Expectations

Scanner outputs and trade story input should expose:

- `scanner_macro_chart_fit_score`
- `scanner_macro_chart_fit_bias`
- `scanner_macro_chart_fit_authority`
- `scanner_macro_chart_fit_components`

Monitor outputs should expose:

- `human_chart_detail_context`
- `human_candle_quality_score`
- `human_vwap_reference_quality_score`
- `human_reward_room_score`
- `human_multi_window_structure_score`

Monitor report/story bullets should expose:

- candle shape: close location, upper wick ratio, lower wick ratio, body ratio
- VWAP reference: explicit Kiwoom/bar VWAP vs session fallback, bar count, explicit VWAP bar count, explicit ratio
- reward room: nearest recent resistance and room/extension percentage

## Follow-Up

- If live runs show the strategist needs more control, add a dedicated `scanner_macro_focus` schema later.
- If valid entries are still missed, tune the monitor candle/reward-room thresholds before broadening the entry rules.
- If bad repeated symbols are still selected, keep that in scanner prior/repeat-loss policy rather than monitor timing logic.
