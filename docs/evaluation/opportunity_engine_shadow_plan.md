# Q11 Opening Surge & Market Reversal Shadow Research

Evaluation program ID: `Q11_OPENING_SURGE_MARKET_REVERSAL`

Q11 is an independent research program running in parallel with Q9 and Q10.
It is not an execution-policy successor to either program.

The fixed research window is `09:00-10:00 KST`. Signals outside this interval
are excluded from Q11 rather than silently mixed into an intraday study.

## Purpose

This module evaluates whether fast market, sector, and symbol transitions can
identify surge opportunities earlier than the current multi-agent pipeline.

It is not a "day after a crash" strategy. A prior market shock is only one
possible input. The engine observes current market transition, breadth, price
acceleration, relative strength, volume, turnover, VWAP, and opening structure.

## Isolation Contract

- Package: `libs/research/opportunity_engine/`
- Runner: `scripts/run_opportunity_engine_shadow.py`
- Output: `reports/evaluation/opportunity_engine_shadow/<day>/`
- Behavior effect: `shadow_only`
- Order execution: prohibited
- Q9 input/output modification: prohibited
- Scanner, Strategist, Commander, and Monitor integration: prohibited

The module may read existing candles, macro snapshots, and the broker cost
profile. It does not write to runtime state and does not participate in the
trading graph.

The regular closeout maintenance regenerates the Q11 report from persisted
minute candles and market snapshots. Q11 generation does not affect Q9 day
validity or promotion decisions.

## v1 Evidence

Market:

- KOSPI200 level and change since the previous snapshot
- market breadth and breadth change
- market transition state

Symbol:

- 1-minute, 3-minute, and 5-minute momentum
- price acceleration
- return from session open
- session-open return minus KOSPI200 day-return proxy
- session VWAP distance
- raw average-volume ratio
- robust median-volume ratio
- turnover acceleration
- 5-minute breakout
- opening-low hold
- short realized range

## State Model

```text
risk_off_continuation
reversal_watch
broad_market_reversal
risk_on_acceleration
neutral
momentum_fading
```

Symbol opportunity states:

```text
weak_or_fading
neutral
surge_watch
entry_ready
```

## Shadow Simulation

`probe_v0` exists only to produce a comparable research baseline.

- entry: opportunity score and minimum momentum/volume/structure evidence
- stop: opening low or bounded short-range stop
- exit: stop, evidence fade, 30-minute timeout, or end of data
- costs: current broker cost profile plus configured slippage

These values are not promoted policy. Later research must compare alternative
entry events, stop rules, maximum holds, and risk budgets on separate training
and validation periods.

## Required Additional Data

The first version uses data already available. The following additions should be
evaluated for availability and quality:

- real-time KOSPI200 futures and futures/spot basis
- sector and theme breadth
- sector turnover concentration
- symbol-to-sector relative strength
- historical time-of-day volume profiles
- order-book imbalance and execution strength

Missing data must be reported as unavailable. It must not be replaced with an
implicit neutral value in promotion analysis.

The current relative-strength value is explicitly a proxy because the existing
intraday candle bundle does not always contain the symbol's previous close.
True symbol-to-index and symbol-to-sector relative return requires synchronized
previous-close data.
