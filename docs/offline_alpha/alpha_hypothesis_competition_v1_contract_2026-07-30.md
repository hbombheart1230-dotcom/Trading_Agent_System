# Alpha Hypothesis Competition v1 Contract

## Purpose

This offline program compares three independent, deterministic entry
hypotheses under one evidence and cost contract.

It does not extend Q18 and does not create a new live numbered validation
phase. It does not change Scanner, Strategist, Commander, Monitor, orders, or
execution.

## Shared Population

Source:

- Scanner/Monitor candidate snapshots in
  `data/logs/quant_shadow_candidates`
- 2026-06-01 through 2026-07-30
- first signal after a 15-minute same-day, same-symbol, same-hypothesis gap
- Kiwoom `ka10080` historical one-minute candles for direct forward
  reconstruction

This is a candidate-space study. It determines whether a simple timing rule
adds value inside the opportunities already surfaced by the system. It is not
a whole-market survivorship-free backtest.

## Frozen Hypotheses

### H1 Opening Risk-Off Reclaim

Scope:

- 09:05 through 10:00 KST
- market rail is `krx_night_futures_gap_down`,
  `risk_off_breadth_collapse`, or `global_risk_off_pressure`

Conditions:

1. VWAP reclaim progress is at least 0.95.
2. Volume ratio is at least 0.80.

Question:

Can a symbol reclaiming VWAP with usable volume during a weak opening produce
a tradable rebound?

### H2 Confirmed Volume Breakout

Conditions:

1. Breakout is confirmed.
2. Volume ratio is at least 1.20.
3. Price is not below VWAP.

Question:

Does a simple confirmed breakout continue far enough to beat costs?

### H3 Confirmed VWAP Pullback

Conditions:

1. VWAP reclaim is confirmed.
2. Pullback structure is valid.
3. Volume ratio is at least 0.80.

Question:

Does the first independent pullback after a confirmed VWAP reclaim produce
repeatable continuation?

## Cost And Horizons

- fixed live cost: 0.28%
- no additional mock-account cost
- horizons: +5m, +15m, +30m, +60m, EOD
- primary decision horizon: +30m
- maximum allowed next-print delay: 180 seconds

## Train And Validation

- train: 2026-06-01 through 2026-06-30
- validation: 2026-07-01 through 2026-07-30
- no threshold optimization
- no parameter grid
- no threshold relaxation after results

## Frozen Gates

Each hypothesis must pass all gates:

- train observed count at least 8
- validation observed count at least 20
- train and validation +30m coverage at least 90%
- train and validation +30m live-net expectancy greater than 0
- validation +30m profit factor at least 1.20
- validation positive-day ratio at least 55%
- validation MDD no worse than -6%
- largest validation day share at most 30%
- largest validation symbol share at most 40%

Decision classes:

- `ELIGIBLE_FOR_SHADOW_INTEGRATION`: every gate passed
- `REJECT`: one or more gates failed

There is no `RETAIN` or automatic extension outcome.

## Isolation

- no LLM
- no runtime graph dependency
- no order intent
- no execution
- no main-system behavior change
- historical cache and generated reports are research artifacts only
