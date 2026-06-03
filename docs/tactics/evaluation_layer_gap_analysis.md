# Evaluation Layer Gap Analysis

Purpose: prepare the bridge from Q8 tactical validation to a higher-level
evaluation loop without changing execution behavior.

Target architecture:

```text
Tactics/Q8
  -> Trade Evaluator
  -> Daily Scorecard
  -> Strategist Feedback
  -> Strategist Input
```

The current tactics layer remains a source of evidence. It is not replaced.

## What Exists

| Component | Current Asset | Reuse Value |
| --- | --- | --- |
| Per-trade read surface | `libs/reporting/trade_read_model.py` | canonical place to normalize trade/report artifact sections |
| Quant tactic day view | `libs/reporting/quant_tactic_evaluation.py` | summarizes tactic outputs and Q8 diagnostics |
| Shadow candidate view | `libs/reporting/quant_shadow_candidate_evaluation.py` | evaluates blocked and alternate candidates |
| Shadow forward outcomes | `libs/reporting/quant_shadow_forward_outcomes.py` | post-decision forward outcome evidence |
| Reporter feedback packet | `libs/reporting/reporter_feedback.py` | existing daily feedback-style aggregation surface |
| Strategist feedback input view | `libs/reporting/strategy_read_model.py` | existing normalized strategist-facing context builder |
| Profitability scorecard | `libs/reporting/profitability_recovery_day1.py` | existing PnL and recovery-oriented daily scorecard logic |
| Operator summary | `reports/operator_summary/...` output family | daily operational status, blocker, route, and trade rollup evidence |

## What Is Missing

| Missing Layer | Gap |
| --- | --- |
| Artifact integrity audit runner | no single read-only report verifies broker truth == lifecycle truth == report truth |
| Formal `trade_evaluator` interface | no stable per-trade evaluation output that combines tactic, PnL, entry, exit, and integrity evidence |
| Unified `daily_scorecard` | existing scorecards are useful but not yet a single daily evaluation contract |
| Strategist feedback bridge | feedback exists, but there is no explicit contract from scorecard findings back to strategist input |
| Required field coverage report | no daily missing/duplicated/unused field surface for Q8 artifacts |
| Validation status surface | no single `PASS/WATCH/FAIL/BLOCKER` result for Q8 validation readiness |

## What Can Be Reused

- Use `trade_read_model.py` as the first source for normalized per-trade facts.
- Use quant tactic evaluation artifacts as evidence, not as duplicated logic.
- Use shadow candidate evaluation and forward outcomes for "would have entered"
  and "blocked candidate quality" questions.
- Use post-exit shadow data to assess early exits and profit fade.
- Use existing reporter and strategist read-model helpers for future feedback
  packets instead of adding another strategist prompt path.
- Use profitability scorecard logic as a source for PnL rollups, but do not let
  it become the only daily scorecard.

## Main Risks

- Duplicate scorecard concepts can create conflicting daily truth.
- Missing broker alignment can make correct strategy evaluation impossible.
- Shadow data can be present but not useful if forward outcome coverage is
  missing.
- Q8 validation can drift into behavior tuning unless reports clearly separate
  evidence from action.

## Recommended Non-Behavior Work Order

1. Add read-only artifact integrity audit output.
2. Define and then implement `trade_evaluation.v1` as a derived read model.
3. Define and then implement `daily_scorecard.v1` as a rollup of trade
   evaluations plus operator summary and broker snapshot.
4. Define strategist feedback as advisory-only output derived from the daily
   scorecard.
5. Only after several validated scorecards, decide whether any tactic should be
   promoted or revised.

## Behavior Boundary

The evaluation layer may produce:

- evidence
- diagnostics
- confidence
- advisory feedback
- candidate patch proposals

The evaluation layer must not directly change:

- entry eligibility
- exit timing
- strategy options
- scanner ranking
- monitor guard conditions
- approval flow
- order placement
