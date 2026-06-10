# News Event Intelligence Plan

Purpose: define how collected news can be converted into human-like event,
theme, and symbol watch evidence without changing trading behavior before Q8
validation and promotion.

This document describes an observation-only layer. It does not authorize new
entry rules, exit rules, scanner ranking changes, monitor guard changes,
Strategist behavior changes, order sizing changes, or execution changes.

## Core Problem

The system already collects candidate and market news, and the Strategist can
read those headlines. That alone is not enough for human-like use of news.

Human traders often do an additional step:

```text
external event
  -> related theme
  -> possible beneficiary symbols
  -> chart/volume/cost confirmation
  -> trade consideration
```

Example:

```text
SpaceX listing news
  -> space / satellite / launch vehicle theme
  -> domestic related-theme watchlist
  -> only consider symbols that pass scanner, monitor, volume, cost, and risk
     gates
```

The goal is to record that reasoning path as evidence, not to let news create
trades by itself.

## Current Implementation Status

Implemented as observation-only:

- `libs/runtime/news_event_intelligence.py`
- Strategist payload field: `news_event_intelligence`
- Strategist output field: `news_event_intelligence`
- Strategist LLM usage field: `news_event_intelligence_usage`
- Strategist raw input field: `news_event_intelligence`
- Strategist summary section: `News Event Intelligence`

Runtime guardrails:

```json
{
  "schema_version": "news_event_intelligence.v1",
  "behavior_effect": "observation_only",
  "promotion_state": "shadow_watchlist",
  "trading_action_allowed": false
}
```

This means the layer can influence what the Strategist discusses, but cannot
override existing scanner, monitor, Commander, cost, volume, or risk gates.

## Layer Responsibilities

| Layer | Question | Output |
| --- | --- | --- |
| News collection | What headlines were collected? | raw candidate and market news samples |
| News sentiment | Is the news broadly positive, negative, or weak? | scored news signal |
| News event intelligence | What event/theme/symbol watch relationships are implied? | observation-only event, theme, and symbol watch evidence |
| LLM Strategist | How should this evidence affect strategic interpretation? | usage explanation and watchlist reasoning |
| Scanner/Monitor/Commander | Is there a valid trade? | existing deterministic gates and final runtime behavior |
| Q8 evaluation | Was the watch evidence useful? | shadow outcome and missed-opportunity comparison |
| Promotion Framework | Should any part become policy? | retain, adjust, promote, reject, or deprecate |

## Event Categories

Initial event categories:

- `ipo_listing`
- `policy_regulation`
- `contract_order`
- `earnings_guidance`
- `supply_chain`
- `theme_momentum`
- `risk_negative`
- `unclassified_theme_signal`

These categories are heuristic labels for observation. They are not trading
signals by themselves.

## Theme Bridge Categories

Initial bridge families:

- `space_aerospace`
- `ai_datacenter`
- `semiconductor`
- `battery`
- `robotics`
- `nuclear`
- `shipbuilding_lng`
- `power_grid`

Each bridge may produce:

- event candidates
- theme watchlist
- symbol watchlist
- required evidence before trade

## Required Evidence Before Trade

The news event layer requires all trading consideration to pass separate
evidence checks:

- `theme_price_confirmation`
- `trading_value_expansion`
- `relative_strength`
- `chart_setup`
- `cost_edge`
- `fresh_news_not_negative`

If these are not present, the news event remains only a watch item.

## Strategist Usage Contract

The Strategist may output:

```json
{
  "news_event_intelligence_usage": {
    "status": "used",
    "used_event_ids": ["news_event_001"],
    "theme_watchlist": ["space_aerospace"],
    "symbol_watchlist": ["005930"],
    "reason": "The news event supports a theme watch, but trade approval still requires monitor and cost confirmation.",
    "observation_only": true
  }
}
```

Allowed statuses:

| Status | Meaning |
| --- | --- |
| `used` | The Strategist referenced the evidence in its interpretation. |
| `ignored` | The evidence was present but not relevant enough. |
| `insufficient` | The evidence was too weak, stale, or unlinked. |

The usage field is an audit trail. It must not be interpreted as approval to
buy or sell.

## Q8 Evaluation Questions

For each news event watch candidate:

- Did the event correctly map to a tradable theme?
- Did related symbols appear in scanner candidates?
- Did related symbols pass or fail cost, volume, and chart gates?
- Did watched symbols outperform ignored symbols?
- Did news-linked watch candidates create missed opportunities?
- Did news-linked watch candidates create false positives?
- Did negative/risk news correctly prevent relaxation?
- Did the Strategist use the event evidence clearly or ignore it correctly?

## Promotion Path

News event intelligence follows the same Promotion Framework lifecycle:

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

Initial decision:

- status: `RETAIN UNDER OBSERVATION`
- behavior: no trading behavior change
- required review: Q8 shadow outcomes plus Strategist effectiveness review

## Promotion Candidates

Possible future promotion candidates:

| Candidate | Promotion Requirement |
| --- | --- |
| Theme watch boost | news-linked theme watch candidates outperform baseline scanner candidates |
| Negative news caution | negative news evidence reduces failed entries without large opportunity cost |
| Event freshness scoring | fresh event candidates outperform stale event candidates |
| Symbol bridge usefulness | bridged symbols show measurable forward strength after event detection |
| Strategist news usage quality | Strategist usage improves candidate choice versus ignoring the event |

No candidate should be promoted from one example.

## Boundary

News event intelligence must not:

- create a direct BUY or SELL instruction
- force a symbol into scanner selection
- bypass cost floor
- bypass volume confirmation
- bypass chart quality gates
- bypass Commander risk controls
- change order size
- change exit policy
- become official policy without Promotion Framework review

Its first job is to make human-like news reasoning observable and measurable.
