# Q9 Master Plan

## Objective

Determine whether the full trading decision chain adds measurable value.

The fixed operational interpretation of this plan is defined by
`q9_full_chain_evaluation_matrix.md`. Q9 is not complete unless Strategist,
Scanner universe/ranking, Commander, Monitor entry, and Monitor exit are all
evaluated separately.

Q9 evaluates:

```text
Commander
  -> Strategist
  -> Scanner
  -> Monitor
  -> Execution
  -> Reporter Feedback
```

The central business questions are:

1. Does Strategist improve results beyond raw Scanner ranking?
2. Does Commander improve or degrade Strategist and Scanner decisions?
3. Does Monitor improve entry timing, or only suppress opportunities?
4. Do exit decisions preserve edge or surrender profit?
5. Does Reporter feedback improve later Strategist decisions?
6. Which parts add value, add no value, or add harmful complexity?

## Architecture

Target read-only modules:

```text
libs/reporting/evaluation/
  contracts.py
  artifact_inventory.py
  trade_read_model.py
  trade_evaluator.py
  counterfactuals.py
  daily_scorecard.py
  strategist_effectiveness.py
  feedback_effectiveness.py
  promotion_review.py
  markdown.py
```

The existing modules under `libs/reporting/` remain evidence providers.
Q9 should wrap or reuse them rather than duplicate their calculations.

## Truth Hierarchy

For realized execution facts:

```text
Kiwoom broker truth
  > reconciled lifecycle
  > deterministic trade summary
  > LLM narrative
```

For decision facts:

```text
canonical decision artifacts
  > event log
  > report interpretation
```

For Q8 counterfactual facts:

```text
trusted deduped same-day forward outcome
  > reconstructed minute-path counterfactual
  > unavailable
```

## Evaluation Units

Q9 uses four different units. They must never be mixed silently.

### Trade Unit

One broker-reconciled lifecycle:

```text
trade_id + symbol + entry fill sequence
```

Used for:

- realized PnL
- entry quality
- exit quality
- tactic alignment

### Decision Window Unit

One Scanner/Strategist/Commander selection opportunity:

```text
day + decision_epoch + candidate_pool_id
```

Used for:

- Scanner Top-1 vs final selected candidate
- Strategist value add
- Commander override value
- runner-up substitution

Canonical decision states:

```text
A = raw Scanner Top-1 before Strategist influence
B = candidate/ranking after Strategist influence
C = Commander final selection or explicit veto/no-trade
```

Q9 must persist A/B/C under the same decision-window identity. It should join
their later outcomes to existing Q8 trusted forward evidence when possible.
It must not create a second generic shadow candidate engine.

### Shadow Candidate Unit

The Q8 canonical key:

```text
day + symbol + baseline_epoch + entry_lane_subtype
```

Used for:

- missed opportunity
- blocked-candidate quality
- alternate candidate performance

### Feedback Opportunity Unit

One feedback recommendation presented before a later decision:

```text
feedback_id + target_pattern + later_decision_id
```

Used for:

- feedback exposure
- adoption
- performance impact

## Core Outputs

### Trade Evaluation

Output:

```text
reports/evaluation/trades/{day}/{trade_id}/trade_evaluation.json
reports/evaluation/trades/{day}/{trade_id}/trade_evaluation.md
```

Required sections:

- integrity status
- realized outcome
- entry quality
- exit quality
- tactic alignment
- candidate-selection context
- Q8 shadow comparison
- evidence references
- defects and watch items

### Daily Scorecard

Output:

```text
reports/evaluation/daily/{day}/daily_scorecard.json
reports/evaluation/daily/{day}/daily_scorecard.md
```

Required sections:

- artifact integrity
- realized performance
- Scanner baseline
- Strategist value add
- Commander value add
- Monitor entry value
- Monitor exit value
- shadow opportunity cost
- market-regime breakdown
- feedback exposure and adoption

### Rolling Scorecards

Output:

```text
reports/evaluation/rolling/{end_day}/scorecard_5d.json
reports/evaluation/rolling/{end_day}/scorecard_10d.json
reports/evaluation/rolling/{end_day}/scorecard_20d.json
```

Purpose:

- avoid making decisions from one day
- show whether effects persist
- identify regime dependence

### Strategist Effectiveness

Output:

```text
reports/evaluation/strategist/{end_day}/strategist_effectiveness.json
reports/evaluation/strategist/{end_day}/strategist_effectiveness.md
```

Comparisons:

- Scanner Top-1
- final candidate after Strategist influence
- candidate after Commander intervention
- no-trade decision vs best trusted shadow candidate

### Feedback Effectiveness

Output:

```text
reports/evaluation/feedback/{end_day}/feedback_effectiveness.json
reports/evaluation/feedback/{end_day}/feedback_effectiveness.md
```

Comparisons:

- feedback exposed vs not exposed
- feedback adopted vs ignored
- before vs after comparable pattern
- benefit vs missed-opportunity side effect

## Scorecard Dimensions

### Performance

- trade count
- win rate
- average net return
- average gain
- average loss
- profit factor
- expectancy
- maximum drawdown
- cost-drag loss rate

### Selection

- Scanner Top-1 forward return
- final selected forward return
- selected-minus-Top-1 delta
- runner-up substitution delta
- no-trade opportunity cost

### Entry

- entry-to-MFE
- entry-to-MAE
- time to MFE
- immediate adverse excursion
- late-entry penalty
- gate correctness

### Exit

- realized return
- MFE captured ratio
- profit fade
- post-exit +5/+15/+30/+60 minute delta
- stop quality
- forced closeout quality

### Strategist

- scenario expectancy
- recommendation expectancy
- theme preference delta
- Scanner override delta
- no-trade correctness
- market-regime alignment

### Feedback

- exposure count
- adoption count
- adoption rate
- performance delta
- pattern reduction
- side-effect penalty
- usefulness score

## Counterfactual Policy

Counterfactuals are necessary because live trade counts are sparse.

Allowed:

- Scanner Top-1 trusted forward outcome
- selected candidate trusted forward outcome
- Q8 blocked-candidate trusted outcome
- post-exit shadow outcome
- reconstructed opening path with explicit confidence label

Not allowed:

- claiming a hypothetical fill from price data alone
- applying future information to an earlier decision
- using current rank as if it were the 09:00 rank
- treating a shadow return as realized PnL

Each counterfactual must include:

- baseline timestamp
- information available at baseline
- forward checkpoints
- fill assumption
- cost assumption
- confidence
- limitations

## Daily Workflow

After Kiwoom regular-session close confirmation:

1. collect broker snapshot
2. reconcile open/closed lifecycles
3. regenerate missing deterministic reports
4. run artifact integrity audit
5. build trade read models
6. evaluate each trade
7. build daily scorecard

After Kiwoom final after-hours close event:

1. refresh post-exit observations
2. refresh Q8 forward outcomes
3. refresh daily scorecard
4. update rolling scorecards
5. update Strategist and feedback effectiveness reviews

Time-based execution remains fallback only.

## Decision Cadence

Daily:

- integrity and data completeness
- descriptive scorecard
- no behavior changes

Every 5 valid trading days:

- directional review
- identify candidate strengths and failures
- no promotion unless contract threshold passes

Every 10 valid trading days:

- Strategist and feedback effectiveness decision
- retain, adjust, reject, or promotion candidate

Every 20 valid trading days:

- policy decay and regime review
- official policy retention/deprecation review

## Q9 Completion Definition

Q9 foundation is complete when:

- one trade is reconstructable from artifacts alone
- Scanner Top-1 vs final selected comparison is available
- Strategist and Commander influence are separately attributed
- entry and exit quality are separately scored
- daily and rolling scorecards are generated deterministically
- feedback exposure and adoption are traceable
- all outputs state evidence type and confidence
- no evaluation output directly changes runtime behavior
