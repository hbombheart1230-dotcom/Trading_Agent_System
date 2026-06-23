# Q9 Full-Chain Evaluation Matrix

Date: 2026-06-22

Status: FIXED EVALUATION SCOPE

This document fixes what Q9 evaluates, when its forward window starts, and
when it must end. It prevents Q9 from becoming another open-ended observation
project.

Q9 is not a Scanner-rank-only review. It evaluates the complete decision
chain and its alternatives.

## Business Question

Q9 must answer:

```text
Did the complete system choose a better candidate, enter it at a better time,
and exit it at a better time than the available alternatives?
```

The answer must be decomposed so that one weak component is not hidden by
another.

## Evaluation Chain

```text
Market and news context
  -> Strategist scenario and policy
  -> Scanner candidate universe and ranking
  -> Commander selection, override, or no-trade
  -> Monitor entry timing or block
  -> Execution
  -> Monitor exit timing
  -> Reporter feedback
```

## Fixed Evaluation Questions

### 1. Strategist

Measure:

- whether the selected market scenario matched subsequent market behavior
- whether Strategist biases improved Scanner ranking
- whether theme, sector, risk, horizon, and playbook guidance added value
- whether no-trade or defensive recommendations avoided losses
- whether Strategist repeatedly pushed the system toward losing patterns

Required comparison:

```text
raw Scanner ranking before Strategist
vs
ranking and candidate after Strategist
```

The Strategist is useful only if it improves cost-adjusted expectancy,
drawdown, or opportunity selection beyond the raw Scanner baseline.

### 2. Scanner Universe And Ranking

Measure two different problems separately:

1. universe recall: did the candidate pool contain later market leaders?
2. ranking precision: did stronger later outcomes receive higher ranks?

Detailed candidate snapshots must cover Top-10 when available.

Report rank buckets:

- rank 1
- ranks 2-3
- ranks 4-5
- ranks 6-10
- outside Top-10, sampled only when a trustworthy source snapshot exists

Compare:

- Top-1 vs best of Top-3
- Top-1 vs best of Top-5
- Top-1 vs best of Top-10
- selected rank vs better-ranked alternatives
- selected rank vs lower-ranked alternatives
- candidate pool vs market/source leaders that were omitted

Top-10 is an evaluation boundary, not an authorization to trade rank 10.
Runtime rank limits remain unchanged until a separate promotion review.

### 3. Commander

Measure:

- whether Commander preserved or changed the Strategist/Scanner selection
- whether a veto correctly avoided a loss
- whether an override selected a better or worse alternative
- whether no-trade decisions created justified protection or opportunity loss

Required comparison:

```text
Strategist-selected candidate
vs
Commander-final candidate or no-trade
```

### 4. Monitor Entry

Measure:

- candidate baseline return if entered immediately
- earliest policy-eligible entry
- actual entry
- delayed entry checkpoints
- blocked candidate outcome
- immediate MAE and later MFE
- late-entry penalty
- guard correctness by blocker and tactic

Required comparisons:

```text
selected baseline
vs earliest eligible entry
vs actual entry
vs no entry
```

This determines whether Monitor timing adds value or merely blocks and delays.

### 5. Monitor Exit And Hold

Measure:

- actual broker-net exit
- MFE and MAE before exit
- captured MFE ratio
- peak-to-exit fade
- post-exit +5/+15/+30/+60 minute outcome
- hard-stop exception
- forced closeout
- same-tactic hold alternatives

Required comparison:

```text
actual exit
vs best executable exit before actual exit
vs +5/+15/+30/+60 minute hold alternatives
```

This answers:

- Was the system too early?
- Did it give back significant profit?
- Would holding longer have improved net expectancy?
- Was an early loss exit still correct because adverse risk expanded?

Post-exit shadow is mandatory for this component.

### 6. Full-System Outcome

Measure:

- realized broker-net expectancy
- win rate
- profit factor
- maximum drawdown
- cost drag
- opportunity cost
- performance by tactic, playbook, market rail, time bucket, rank bucket, and
  intended horizon

The full-system score cannot identify component value by itself. It must be
reported alongside the five component comparisons above.

## Required Counterfactual Record

One decision-window record must preserve:

```text
decision_id
decision_epoch
candidate_pool_id
market_regime
raw Scanner Top-10
post-Strategist Top-10
Strategist selection
Commander final selection or veto
Monitor entry eligibility timeline
actual execution
Monitor exit timeline
trusted forward outcomes
post-exit outcomes
```

Evidence must remain separated:

- `REALIZED`
- `TRUSTED_SHADOW`
- `RECONSTRUCTED`
- `UNAVAILABLE`

## Q9 Start Gate

The fixed forward evaluation window must not start until all items pass:

| Gate | Required state |
| --- | --- |
| Raw Scanner snapshot | pre-Strategist Top-10 or full available ranking persisted |
| Strategist snapshot | post-Strategist ranking and selection persisted |
| Commander snapshot | final selection, veto, and reason persisted |
| Monitor entry timeline | selected baseline, eligible time, actual entry/block persisted |
| Monitor exit timeline | actual exit plus MFE/MAE and post-exit joins available |
| Broker integrity | broker/lifecycle/report truth aligned |
| Baseline freeze | policy, prompt, tactic, cost, Q8, and Q9 versions recorded |
| Coverage | at least 95% of required comparison fields populated or explicitly unavailable with a valid reason |

As of 2026-06-22 this gate does not pass:

- Scanner vs Strategist comparable count is 0
- Commander alternatives are unavailable
- entry counterfactuals are not calculated
- exit quality remains `diagnostic_only`
- post-exit comparison remains unavailable in Q9 outputs

The historical component review issued bounded decisions despite this gate:

- Scanner: `ADJUST_AND_RETEST`
- Strategist: `INSUFFICIENT_EVIDENCE`
- Commander: `INSUFFICIENT_EVIDENCE`
- Monitor entry: `RETAIN`
- Monitor exit: `INSUFFICIENT_EVIDENCE`
- full system: `REJECT`

See `q9_component_decision_2026-06-22.md`. No new evaluation component may be
added to compensate for a missing A/B/C control.

Forward instrumentation status after the 2026-06-22 patch:

- ranking-control A, Strategist B, and final approval/veto C share one
  `decision_id`
- Q9-only forward candidates preserve A/B/C symbols through
  +5/+15/+30/+60 minute outcome attachment
- A is a same-universe intrinsic Scanner ranking control
- the Strategist candidate-universe effect remains unavailable because the
  candidate source pool is created with Strategist guidance
- Q8 candidate aggregates do not consume Q9 A/B/C forward candidates

Therefore existing Q9 outputs are a useful realized-performance backfill, but
they are not a completed full-chain Q9 evaluation window.

## Fixed Evaluation Period

### Stage 0 - Readiness

Duration:

```text
No calendar waiting.
Complete and verify the Start Gate.
```

Only observability, joins, backfill, and evaluation code may change.
Trading behavior remains frozen.

### Stage 1 - Historical Backfill

Use all reconstructable data under one baseline version.

Purpose:

- populate immediate directional findings
- identify fields that cannot be reconstructed
- avoid discarding the existing month of evidence

Reconstructed evidence remains separate and cannot alone promote policy.

### Stage 2 - Fixed Forward Window

Duration:

```text
5 consecutive valid trading days after the Start Gate passes
```

A valid day requires:

- runtime coverage for the active session
- at least 95% comparison-field coverage
- no unresolved integrity blocker
- policy baseline unchanged

The five-day window is not extended because results are poor, mixed, or
unfavorable.

### Stage 3 - Mandatory Decision

At the end of day 5, issue one decision for every component:

- `RETAIN`
- `PROMOTION_CANDIDATE`
- `ADJUST_AND_RETEST`
- `REJECT`
- `DEPRECATE_CANDIDATE`
- `INSUFFICIENT_EVIDENCE`

`INSUFFICIENT_EVIDENCE` must name the exact missing comparison. It may not be
used as a general reason to wait longer.

## Evidence Thresholds

Apply the Q9 contract:

| Finding | Minimum |
| --- | --- |
| Directional | 20 comparable observations, 2 valid days, 90% integrity |
| Promotion candidate | 50 comparisons, 3 valid days, 95% integrity, cost-positive effect |
| Strong policy decision | 100 comparisons, 5 valid days, at least 2 market regimes |

Decision-window and shadow observations, not only realized trades, count
toward selection and timing comparisons. Evidence classes remain separate.

## Q8 Relationship

Q8 is closed for its original question:

```text
Should the observed tactical blockers or relaxations be promoted?
```

Q8 produced no new positive policy candidate. It did produce:

- rejected relaxations
- retained defensive concepts
- trusted blocked-candidate outcomes
- conditional questions handed to Q9

Q9 must not reopen Q8. It uses Q8 evidence to answer broader component-value
questions.

## Change Freeze

During the five-day forward window:

- no entry or exit rule changes
- no tactic additions
- no rank-limit changes
- no Scanner weight changes
- no Strategist prompt changes
- no Commander authority changes

Critical artifact defects may be repaired. If a repair changes evidence
meaning, only the affected component window restarts. The entire Q9 program
does not restart automatically.

## Completion Definition

Q9 is complete only when it answers all of the following:

1. Does Strategist improve raw Scanner output?
2. Does Scanner contain and rank worthwhile candidates?
3. Does Commander improve final selection or no-trade decisions?
4. Does Monitor improve entry timing?
5. Does Monitor improve exit timing?
6. Does the integrated system produce positive net value after costs?

A report containing only realized PnL or Scanner rank statistics is not Q9
completion.
