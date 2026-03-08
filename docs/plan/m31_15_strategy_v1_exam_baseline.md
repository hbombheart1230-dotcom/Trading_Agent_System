# M31-15 Strategy V1 Exam Baseline Freeze

- Date: 2026-03-08
- Objective: freeze one minimal, reproducible strategy package for mock investor exam operations.

## Primary Strategy

- strategy: `regime_momentum_v1`
- version: `regime_momentum_v1`
- reason: deterministic behavior, already integrated with data-quality status, sizing risk-context, and explainable decision packet fields.

## Frozen Package Manifest

- manifest path: `config/strategy_v1_exam_baseline.json`
- baseline version: `m31.exam.baseline.2026-03-08`

This manifest locks:

- runtime policy (`staging/mock/manual`, execution enabled, real execution disabled)
- universe/session policy and source weights
- required deterministic feature set
- entry/exit/sizing/invalidation policy
- reproducibility keys and required artifacts

## Exam Scope Contract

1. Universe/session policy
- `use_universe_builder=true`
- `candidate_source=top_picks`
- `candidate_topk=5`
- weighted multi-source ranking retained

2. Entry/NOOP/Exit rules
- entry: composite/signal/news/volatility gate
- NOOP: entry conditions not met or sizing qty zero
- exit: composite floor, invalidation trigger, and exit-policy rule bridge

3. Sizing policy
- risk-aware sizing through:
  - `regime`
  - `volatility_percentile`
  - `portfolio_exposure`
  - `correlation_bucket`
  - `daily_loss_state`
  - `degrade_mode`

4. Invalidation policy
- signal floor breach
- volatility guard for high-volatility regime

## Reproducibility Rule

- Daily mock exam run must keep:
  - strategy name fixed to `regime_momentum_v1`
  - approval mode fixed to `manual`
  - risk limits unchanged intraday
- Any parameter change is allowed only once per day after closeout review and must be documented in a new baseline manifest version.
