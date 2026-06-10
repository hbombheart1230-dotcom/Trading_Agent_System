# Trading Tactics Baseline

This folder is the operator-facing baseline for tactical trading changes.

Use it before changing runtime strategy, scanner selection, monitor entry/exit,
cache routing, or reporting rules. Daily patch notes record what changed; this
folder records what the system is trying to optimize and which rules are
allowed to change behavior.

## Files

- `tactical_operating_baseline.md`: current tactical policy, guardrails,
  open problems, and patch queue.
- `quant_tactic_engine_plan.md`: modular plan for adding a quant-style tactic
  layer without replacing the current commander, strategist, scanner, monitor,
  execution, reporting, and memory flow.
- `quant_tactic_engine_phase_plan.md`: phase and slice plan for implementing
  the quant tactic layer with modularity and minimal runtime disruption.
- `intraday_validation_checklist.md`: Q8 live validation checklist for
  confirming tactical evidence before additional behavior changes.
- `artifact_integrity_audit.md`: read-only audit template for broker,
  lifecycle, report, tactic, shadow, and post-exit artifact consistency.
- `evaluation_layer_gap_analysis.md`: gap analysis for the future
  Trade Evaluator -> Daily Scorecard -> Strategist Feedback bridge.
- `evaluation_layer_schemas.md`: proposed read-only schemas and interfaces for
  the higher-level evaluation layer.
- `strategist_effectiveness_review.md`: methodology for measuring whether
  Strategist decisions add value beyond raw Scanner output.
- `feedback_effectiveness_review.md`: methodology for measuring whether
  Reporter -> Strategist feedback improves future decisions.
- `promotion_framework.md`: governance process for deciding when experimental
  observations, tactics, evaluations, or feedback become official policy.
- `market_regime_rail_plan.md`: plan for connecting global/domestic market
  information to Strategist-selected, measurable market regime rails.
- `news_event_intelligence_plan.md`: observation-only plan for converting
  collected news into event, theme, and symbol watch evidence before any
  behavior promotion.
- `q8_shadow_evaluation_operating_plan.md`: daily operating plan for reviewing
  Q8 shadow data, blocked candidates, missed opportunities, and promotion
  candidates.
- `q8_entry_lane_observation_plan.md`: observation-only plan for splitting all
  major entry lanes into measurable subtypes before any additional behavior
  promotion.
- `q8_daily_review_2026-06-02.md`: first post-close Q8 review using the
  2026-06-02 live/shadow dataset and the repaired broker/lifecycle integrity
  surface.
- `q8_daily_review_2026-06-04.md`: post-close Q8 review using the 2026-06-04
  live/shadow dataset, repaired closeout ordering, and completed post-exit EOD
  recap.
- `q8_historical_review_2026-05-18_to_2026-06-08.md`: historical review that
  separates live-trade performance, Q8 shadow evidence, market regime rail
  availability, and broker-truth artifact eras.
- `q8_below_vwap_reclaim_subtype_review_2026-05-18_to_2026-06-08.md`:
  subtype review for `below_vwap_reclaim_not_ready`; concludes that global
  relaxation is not justified and `below_vwap_reclaim_classifier_v2` should be
  observed before behavior promotion.

## Evaluation & Promotion Hierarchy

```text
Q8 Tactical Validation
  -> Q8 Shadow Evaluation
  -> Market Regime Rail Observation
  -> News Event Intelligence Observation
  -> Artifact Integrity
  -> Trade Evaluator
  -> Daily Scorecard
  -> Strategist Effectiveness Review
  -> Feedback Effectiveness Review
  -> Promotion Framework
  -> Strategist Feedback
  -> Future Strategy Improvement
```

- Q8 validates tactical behavior: cost floor, pullback quality, runner-up
  review, shadow candidates, and quant tactic selection.
- Q8 Shadow Evaluation determines whether blocked candidates were correctly
  blocked or became missed opportunities.
- Market Regime Rail Observation connects global/domestic market context to
  measurable Strategist-selected rails without replacing the LLM Strategist.
  KOSPI200 and KRX KOSPI200 night futures are pre-open/regular-session context
  inputs only until promoted through the Promotion Framework.
- News Event Intelligence Observation connects collected headlines to
  event/theme/symbol watch evidence. It is only a watch layer until Q8,
  Strategist Effectiveness, and the Promotion Framework show measurable value.
- Artifact Integrity validates whether broker truth, lifecycle truth, report
  truth, tactic evidence, and shadow evidence are complete and consistent.
- Trade Evaluator and Daily Scorecard convert trustworthy artifacts into
  read-only evaluation outputs.
- Strategist Effectiveness validates whether the LLM Strategist contributes
  measurable value beyond Scanner output.
- Feedback Effectiveness validates whether the Reporter -> Strategist learning
  loop improves later decisions.
- Promotion determines whether trustworthy and useful observations become
  official trading policy.
- Strategist Feedback should remain advisory until the evidence supports a
  separate behavior-change review.

In short:

- Validation determines whether observations are trustworthy.
- Evaluation determines whether observations are useful.
- Promotion determines whether observations become policy.

## Update Rule

Every tactical patch should update `tactical_operating_baseline.md` when it:

- changes entry eligibility
- changes exit timing
- changes strategist/scanner/monitor authority
- changes cache routing that affects LLM refresh frequency
- changes carry or horizon behavior
- promotes an observation-only signal into behavior

Do not use this folder for broad refactor notes. Keep refactor progress in
`docs/daily_patch` or `docs/dev`.

## Current Review State

Latest completed review:

- 2026-06-08 post-close reconciliation and risk-off review

Current conclusions:

- Artifact integrity is now the first gate. Broker truth, lifecycle truth, and
  report truth must align before tactic conclusions are considered.
- `broker_closed_report_open_count` must remain 0 after close. Any non-zero
  value is a Q8 blocker until repaired.
- Cost-edge/cost-floor is already promoted as a monitor hard gate. Do not
  re-promote it.
- VWAP pullback quality gate remains promoted and should continue to be
  measured for missed opportunity cost.
- `risk_off_defensive_observe_no_entry_policy` is promoted as a narrow monitor
  hard gate: when the market rail is risk-off and the selected tactic is
  `defensive_observe`, a triggered BUY is blocked unless Commander records an
  explicit risk-off exception override. This prevents observe/no-trade posture
  from becoming a live entry tactic.
- `below_vwap_reclaim_not_ready` is the next over-blocking review target.
  The blocker is retained, but Q8 now separates true below-VWAP failures from
  near-reclaim, reclaim-in-progress, and post-reclaim pullback candidates.
- `below_vwap_reclaim_classifier_v2` is observation-only and further splits
  below-VWAP cases into deep failure, ordinary failure, shallow rebound,
  index/large-cap rebound, near-reclaim, and confirmed post-reclaim pullback.
- Pullback maturity, volume confirmation, breakout readiness, opening momentum,
  largecap surge, runner-up selection, human chart sanity, and cost-edge states
  are now split into observation-only `entry_lane_observation` lanes. This is
  evidence collection only, not a new entry rule.
- The next 3 to 5 live sessions should be reviewed by lane/subtype/time bucket
  before promoting another behavior change.
- Post-exit EOD tracking must remain complete after closeout; the 2026-06-04
  recap repaired EOD from pending to observed through fresh minute fetch.
- Market regime rails remain observation-only until their evidence is attached
  to Q8/shadow outcomes.
- News event intelligence is observation-only. It may help the Strategist
  explain event/theme/symbol watch relationships, but it must not bypass
  scanner, monitor, Commander, cost, volume, or risk gates.

## Validation Boundary

Validation documents in this folder are evidence contracts only. They do not
authorize new trading behavior, entry logic, exit logic, strategy changes, guard
changes, or approval-flow changes.
