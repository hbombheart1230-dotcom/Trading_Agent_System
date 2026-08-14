# M4 Opportunity, Strategy, and Market Source Audit - 2026-08-14

## Scope

M4 adds display-only read models for opportunities, strategy performance, and
market context. It does not execute an evaluation, call a provider, alter an
artifact, or import Trading Core code.

Public routes:

```text
GET /api/v1/opportunities/funnel
GET /api/v1/opportunities/outcomes
GET /api/v1/strategies/performance
GET /api/v1/market/snapshot
GET /api/v1/market/series
```

The public concepts are `Opportunity`, `StrategyPerformance`, and
`MarketSnapshot`. Evaluation phase names are not primary response fields.

## Opportunity Sources

| Public surface | Accepted source | Behavior effect |
| --- | --- | --- |
| current shadow signals | `opportunity_engine_signals.json` | `SHADOW_ONLY` |
| blocker outcome summary | `q8_shadow_blocker_review.json` | `SHADOW_ONLY` |
| opening forward outcomes | `opening_rank1_shadow_daily.json` | `OBSERVATION_ONLY` |

The funnel reads the latest signal for each symbol while preserving the total
signal count. It also exposes raw, deduplicated, and duplicate candidate counts
so repeated observations are not mistaken for independent samples.

Forward outcomes retain gross, live-equivalent net, and mock-broker net values
as separate fields. They are never merged with realized trade performance.
Pending checkpoints reduce coverage and produce `PARTIAL`, not a fabricated
zero return.

The API intentionally does not read `q9_decision_windows.json`. The current
file is approximately 82 MB and is outside the request-time bounded-read
contract.

## Strategy Performance Authority

Strategy breakdowns reuse the M3 normalized trade list. The metric authority
is the trusted realized return already labeled `MOCK_BROKER_NET`.

Supported dimensions:

```text
playbook
tactic
setup
horizon
theme
```

`setup` is a display alias over the canonical tactic identifier. A trade with
multiple themes contributes to each theme group, but it contributes only once
to the response-level trade count. Missing dimensions are shown as
`UNSPECIFIED`; they are not silently dropped.

The breakdown returns trade count, resolved count, win/loss/flat counts,
coverage, win rate, average return, profit factor, and additive-return maximum
drawdown. Unsupported or missing values remain null.

## Market Authority

The accepted source is:

```text
data/logs/macro_indicators/YYYY-MM-DD/latest.json
```

The snapshot normalizes the existing indicator map without fetching fresh
data. It includes rates, currencies, domestic and global equity indices, and
KRX night futures when present. Sentiment and Korean market breadth remain
explicit source fields.

The series endpoint reads at most one bounded `latest.json` per requested day,
enforces the shared maximum period, and accepts only a constrained metric key.
Missing days are counted rather than represented as zero.

## Actual Artifact Check

Actual artifacts checked on 2026-08-14:

| Surface | Result |
| --- | --- |
| 2026-08-13 opportunity signals | 168 total signals, 3 current symbol signals |
| 2026-08-13 opening outcomes | 8 opportunities, 39/40 checkpoints observed, 97.5% coverage |
| 2026-06-01..2026-07-31 strategy rows | 110 trades |
| 2026-08-14 market snapshot | 15/15 indicators available, no sanity warning |
| 2026-08-10..2026-08-14 KOSPI series | 5 source days available |

The strategy response is `PARTIAL` because the historical read model contains
performance fallback rows and missing strategy fields. This is a truthful
artifact coverage result, not an API calculation failure.

## Safety Boundary

M4 retains all existing isolation rules:

* GET-only routes;
* bounded JSON reads;
* no file writes;
* no network or broker calls;
* no Trading Core, graph, execution, or script imports;
* no evaluation generator invocation;
* no behavior change.

M4 is suitable as the data contract for the Opportunities, Strategies, and
Market UI pages. Evaluation provenance may be shown in drill-down diagnostics,
but Q-phase progress must not become the product navigation model.
