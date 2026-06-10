# Market Regime Rail Plan

Purpose: define how global and domestic market information should become a
measurable strategy rail without replacing the LLM Strategist.

This document is a plan only. It does not change runtime behavior, strategy
options, scanner ranking, monitor rules, guard thresholds, Strategist prompts,
report generation, or execution logic.

## Core Principle

Market information already enters the Strategist input. A market regime rail is
not a replacement for that LLM reasoning.

The difference is:

| Layer | Question | Output |
| --- | --- | --- |
| Market data input | What is happening in the market? | indices, rates, FX, VIX, breadth, sentiment |
| LLM Strategist | How should this market be interpreted? | scenario, thesis, themes, candidate direction |
| Market regime rail | How should that interpretation be evaluated operationally? | measurable rail id and expected tactical behavior |
| News event intelligence | Which event/theme/symbol relationships are worth watching? | observation-only event and watchlist evidence |
| Q8/shadow evaluation | Did that rail improve decisions? | evidence, deltas, promotion candidate status |

The rail converts Strategist interpretation into a repeatable evaluation frame.
It does not decide trades by itself.

News event intelligence is separate from the market regime rail. The market
rail describes the broad operating environment. News event intelligence
describes event-specific watch evidence, such as an external listing, policy,
contract, supply-chain, or risk headline that may map to themes or symbols.
Both layers start as `observation_only`.

## Current Market Inputs

The system already collects and stores:

- KOSPI
- KOSDAQ
- KOSPI200
- KRX KOSPI200 night futures
- domestic market breadth
- S&P 500
- NASDAQ
- Dow
- VIX
- DXY
- USD/KRW
- USD/JPY
- USD/CNY
- EUR/USD
- US 2Y yield
- US 10Y yield
- Korea 3Y yield
- Korea 10Y yield
- global sentiment score
- macro stress flags

These inputs are already visible in Strategist artifacts and reports. The
missing layer is a formal rail that makes the interpretation measurable.

KRX KOSPI200 night futures is treated as pre-open derivatives pressure. It is
useful when the next regular session is likely to open with a broad gap-down or
gap-up. The first implementation status is `observation_only`; it gives the
Strategist and Q8 review a measurable input, but it does not block trades,
force entries, change order size, or override monitor rules.

## LLM Strategist Role

The Strategist remains responsible for:

- interpreting the market regime
- identifying scenario hypotheses
- selecting or proposing a rail
- explaining sector/theme preference
- identifying exceptions
- reviewing whether its prior interpretation was correct

The rail should make the Strategist more measurable, not less important.

## Rail Role

The rail is responsible for:

- naming the operating context
- recording expected tactical behavior
- making Scanner/Monitor outcomes comparable across similar contexts
- supporting shadow evaluation
- supporting Promotion Framework decisions
- allowing later comparison with news-event watch evidence

The rail must start as `observation_only`.

## Proposed Rail Candidates

| Rail ID | Market Conditions | Strategist Meaning | Evaluation Focus |
| --- | --- | --- | --- |
| `risk_off_breadth_collapse` | KOSPI/KOSDAQ weak, breadth weak, FX/DXY pressure | avoid broad chase; prefer confirmed relative strength | did filters avoid losers without missing true leaders? |
| `krx_night_futures_gap_down` | KRX KOSPI200 night futures down sharply before/near open | expect broad gap-down pressure; require confirmed relative strength | did pre-open pressure explain missed/blocked opportunities or avoided losses? |
| `krx_night_futures_gap_up` | KRX KOSPI200 night futures up sharply before/near open | opening risk-on pressure with possible gap chase risk | did opening momentum entries outperform delayed pullback entries? |
| `us_tech_risk_on_korea_weak` | US tech positive while Korean indices are weak | selective large-cap tech or semiconductor strength | did relative strength candidates outperform broad market? |
| `panic_rebound_candidate` | domestic selloff with isolated reclaim/breakout strength | look for rebound only after structure confirms | did reclaim/breakout beat passive avoidance? |
| `liquidity_leader_rotation` | market weak but liquidity concentrates in a few leaders | leader-only participation | did high-liquidity leaders justify relaxed confirmation? |
| `defensive_rotation` | risk-off with defensive themes or cash-flow themes | lower beta, lower chase, stricter cost edge | did defensive symbols reduce drawdown? |
| `macro_pressure_no_trade` | risk-off plus poor breadth plus no relative strength | observe only | did no-trade preserve capital without large opportunity cost? |

Rail definitions are evaluation candidates. They are not official policy until
the Promotion Framework approves them.

## Rail Selection Target

Future Strategist output may include:

```json
{
  "market_regime": "risk_off",
  "market_regime_rail": "risk_off_breadth_collapse",
  "rail_confidence": "medium",
  "rail_rationale": "KOSPI/KOSDAQ and breadth are deeply negative while FX pressure is elevated.",
  "expected_tactical_behavior": [
    "avoid weak-volume pullback chase",
    "prefer confirmed reclaim or relative strength breakout",
    "treat runner-up substitution conservatively"
  ]
}
```

This is a future schema target. It is not a prompt or runtime change yet.

## Shadow Evaluation Fields

When implemented later, the rail should be recorded in shadow artifacts:

```json
{
  "schema_version": "market_regime_rail_shadow.v1",
  "behavior_effect": "observation_only",
  "rail_id": "",
  "rail_source": "strategist|deterministic_classifier|mixed",
  "market_inputs": {
    "kospi_pct": null,
    "kosdaq_pct": null,
    "kospi200_pct": null,
    "krx_night_futures_pct": null,
    "breadth": null,
    "nasdaq_pct": null,
    "sp500_pct": null,
    "vix_level": null,
    "vix_change_pct": null,
    "dxy_pct": null,
    "usdkrw_pct": null
  },
  "expected_tactical_behavior": [],
  "candidate_fit": {
    "selected_symbol": "",
    "scanner_top1_symbol": "",
    "rail_fit_score": null,
    "rail_fit_tier": ""
  },
  "evaluation": {
    "selected_outcome": {},
    "scanner_top1_outcome": {},
    "blocked_candidate_outcomes": []
  }
}
```

## Evaluation Questions

For each rail:

- Did the Strategist choose the right rail?
- Did the rail match the actual market behavior?
- Did selected candidates outperform Scanner Top-1?
- Did blocked candidates underperform selected candidates?
- Did the rail reduce drawdown?
- Did the rail create missed opportunity cost?
- Did the rail improve expectancy?
- Did the rail improve profit factor?

## Promotion Path

Market regime rails follow the same lifecycle as other tactics:

```text
Observation
  -> Validation
  -> Evaluation
  -> Promotion Candidate
  -> Controlled Adoption
  -> Official Policy
  -> Ongoing Review
  -> Retain / Adjust / Deprecate
```

Initial status for every market rail:

- `behavior_effect`: `observation_only`
- Promotion decision: `RETAIN UNDER OBSERVATION`
- Minimum review: multiple live days plus shadow observations

## Boundary

Market regime rails must not initially:

- block trades
- force entries
- override cost floor
- override volume confirmation
- override monitor exits
- change order size
- change broker execution

Their first job is to make the Strategist's market interpretation measurable.
