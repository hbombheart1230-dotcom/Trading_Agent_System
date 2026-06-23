# Trading Tactics Baseline

This folder is the operator-facing baseline for tactical trading changes.

## Evaluation Status

Q8 tactical validation is closed. The current evaluation authority is:

```text
docs/evaluation/current_operating_baseline.md
docs/evaluation/q8_closure_lock.md
```

Documents in this folder remain authoritative for tactic definitions,
historical rationale, and Q8 evidence interpretation. They do not reopen Q8 or
define the active Q9 work queue.

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
- `q8_evaluation_contract.md`: canonical Q8 evaluation contract. It fixes the
  dedupe key, trusted forward outcome definition, trust gate thresholds, and
  change-control rule for Q8 promotion evidence.
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
  blocked or became missed opportunities. Promotion review must use trusted
  same-day forward outcomes and deduped candidates only; stale cross-day
  checkpoints are evidence defects, not performance data.
- Q8 Evaluation Contract is the authority for dedupe, trusted forward, trust
  gate, and promotion eligibility. If another Q8 document conflicts with the
  contract, the contract wins.
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
- Trust Gate determines whether Q8 evidence is eligible for promotion review.

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

- `docs/evaluation/q8_final_comprehensive_review_2026-06-20.md`

Current conclusions:

- Q8 is closed with no new tactic promoted.
- Q8 must not be reopened for opening overshoot, isolated winners, weak live
  performance, or missing Q9 attribution. Similar future research requires a
  new contract and does not alter the historical Q8 decision.
- Broad VWAP reclaim, pullback-quality, and opening-momentum relaxations were
  rejected.
- Automatic runner-up substitution remains prohibited.
- Existing Q8 shadow collection may continue only as an evidence source for
  Q9.
- Q9 must complete Scanner A -> Strategist B -> Commander C decision-window
  linkage before claiming Strategist or Commander value.
- There is no active instruction to restart a generic 3-to-5-day Q8
  observation window.
- No behavior change is authorized without a separate promotion review.

## Validation Boundary

Validation documents in this folder are evidence contracts only. They do not
authorize new trading behavior, entry logic, exit logic, strategy changes, guard
changes, or approval-flow changes.
