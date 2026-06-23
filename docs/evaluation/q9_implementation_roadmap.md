# Q9 Implementation Roadmap

## Delivery Strategy

Q9 is implemented as a read-only reporting workstream.

No phase may change trading behavior.

Estimated implementation:

```text
5 phases
10 slices
approximately 8-12 focused coding turns
```

The work should be completed in order. A later phase must not invent a second
truth model to bypass an earlier phase.

## Phase Q9.1 - Contract And Inventory

### Slice Q9.1.1 - Artifact Inventory

Create:

```text
libs/reporting/evaluation/artifact_inventory.py
```

Responsibilities:

- enumerate broker, lifecycle, report, Q8, shadow, post-exit, Strategist,
  Scanner, Monitor, and feedback artifacts
- return paths, timestamps, schema versions, and missing reasons
- avoid full scans of the multi-gigabyte `events.jsonl`
- prefer trade directories, daily indexes, canonical artifacts, and bounded
  event-tail/index readers

Output:

```text
artifact_inventory.v1
```

### Slice Q9.1.2 - Contract Types

Create:

```text
libs/reporting/evaluation/contracts.py
```

Responsibilities:

- evidence classes
- integrity statuses
- decision classes
- contract version
- validation helpers

Verification:

- schema tests
- invalid evidence-class rejection
- version field required

## Phase Q9.2 - Canonical Trade Evaluation

### Slice Q9.2.1 - Trade Read Model Adapter

Create:

```text
libs/reporting/evaluation/trade_read_model.py
```

Reuse:

- `libs/reporting/trade_read_model.py`
- broker reconciliation outputs
- lifecycle bundles
- deterministic summaries

Responsibilities:

- normalize one trade
- attach evidence provenance
- identify missing and conflicting fields
- choose authoritative PnL

### Slice Q9.2.2 - Trade Evaluator

Create:

```text
libs/reporting/evaluation/trade_evaluator.py
```

Responsibilities:

- entry quality
- exit quality
- tactic alignment
- cost impact
- Q8 comparison
- defect/watch classification

Outputs:

```text
trade_evaluation.v1
```

Verification:

- profitable trade
- losing trade
- cost-drag trade
- broker/lifecycle conflict
- missing exit
- post-exit early-exit case

## Phase Q9.3 - Counterfactual And Attribution

### Slice Q9.3.1 - Decision Window Reconstruction

Create:

```text
libs/reporting/evaluation/counterfactuals.py
```

Responsibilities:

- Scanner Top-1 baseline
- Strategist-selected candidate
- Commander-final candidate
- no-trade baseline
- evidence confidence

Hard rule:

- never use current ranking as historical ranking
- reconstructed opening analysis remains `RECONSTRUCTED`

### Slice Q9.3.2 - System Attribution

Create attribution records:

```text
scanner_baseline
strategist_delta
commander_delta
monitor_entry_delta
monitor_exit_delta
system_delta
```

Verification:

- Strategist keeps Top-1
- Strategist replaces Top-1
- Commander vetoes Strategist
- Monitor blocks candidate
- missing alternate outcome

## Phase Q9.4 - Scorecards

### Slice Q9.4.1 - Daily Scorecard

Create:

```text
libs/reporting/evaluation/daily_scorecard.py
libs/reporting/evaluation/markdown.py
```

Inputs:

- trade evaluations
- decision-window comparisons
- Q8 daily evaluation
- operator summary
- broker snapshot

Outputs:

```text
daily_scorecard.v1
```

### Slice Q9.4.2 - Rolling Scorecards

Create:

```text
libs/reporting/evaluation/rolling_scorecard.py
```

Windows:

- 5 valid days
- 10 valid days
- 20 valid days

Aggregation rules:

- separate policy baseline versions
- separate evidence classes
- include market-regime breakdown
- report sample concentration

## Phase Q9.5 - Strategist And Feedback Effectiveness

### Slice Q9.5.1 - Strategist Effectiveness

Create:

```text
libs/reporting/evaluation/strategist_effectiveness.py
```

Evaluate:

- scenario value
- recommendation value
- theme/sector preference value
- Scanner override value
- no-trade correctness
- market-regime interpretation

### Slice Q9.5.2 - Feedback Effectiveness And Review

Create:

```text
libs/reporting/evaluation/feedback_effectiveness.py
libs/reporting/evaluation/promotion_review.py
```

Evaluate:

- feedback exposure
- adoption
- performance delta
- side effects
- usefulness score

Output decisions remain advisory.

## Runtime Integration

Q9 generation hooks:

### Regular Close Event

Kiwoom market status:

```text
4 or 8
```

Run:

- broker reconciliation
- artifact inventory
- trade evaluations
- initial daily scorecard

### Final After-Hours Event

Kiwoom market status:

```text
b, d, or 9
```

Run:

- post-exit refresh
- Q8 forward refresh
- final daily scorecard
- rolling scorecards
- Strategist effectiveness
- feedback effectiveness

Time-based 16:00 execution remains fallback only.

## Testing Matrix

### Unit Tests

- schema validation
- truth precedence
- integrity classification
- cost-adjusted return
- profit factor and expectancy
- MDD
- Scanner/Strategist/Commander deltas
- feedback adoption

### Fixture Tests

Required fixtures:

- normal profitable trade
- normal losing trade
- split sell
- carryover trade
- forced closeout
- broker closed/report open mismatch
- no-trade day
- missing Q8 forward evidence
- Strategist override
- Commander veto

### Regression Tests

- existing report files remain unchanged
- no execution imports from evaluation modules
- no Q9 output is read by Monitor, Scanner, Commander, or execution
- Q8 contract and Q9 contract remain separate

## Completion Gates

### Gate A - Integrity

- all fixture trades reconstruct
- broker truth precedence passes
- no duplicate trade identity

### Gate B - Attribution

- Scanner, Strategist, Commander, Monitor contributions are independently
  visible
- unavailable comparisons remain unavailable rather than fabricated

### Gate C - Scorecards

- daily output deterministic
- rolling windows deterministic
- baseline versions separated

### Gate D - Safety

- evaluation package has no runtime behavior dependency
- generated feedback is advisory only
- no prompts or policies are modified

## First Operational Review

After implementation:

1. backfill the most recent 10 valid trading days
2. mark legacy/incomplete days explicitly
3. produce the first 5-day and 10-day scorecards
4. answer the first Q9 decision:

```text
Does Strategist outperform Scanner Top-1 after controlling for Commander,
Monitor, costs, integrity, and market regime?
```

The first Q9 review must produce a decision class. It must not end with an
unbounded request for more observation.

## Implementation Checkpoint - 2026-06-19

Completed:

- Q9.1.1 artifact inventory
- Q9.1.2 contract types
- Q9.2.1 trade read model adapter
- Q9.2.2 deterministic trade evaluator foundation
- Q9.3.1 attribution record surface
- Q9.3.2 explicit unavailable-delta handling
- Q9.4.1 daily scorecard
- Q9.4.2 5/10/20-day rolling scorecards
- Q9.5.1 Strategist effectiveness surface
- Q9.5.2 feedback effectiveness surface
- recent 10 artifact-bearing trading-day backfill

Validation:

- 17 focused Q9, trade-read-model, and Q8 regression tests pass
- evaluation package is not imported by runtime trading modules
- all generated files are isolated below `reports/evaluation/`

First backfill result:

```text
realized eligible trades: 34
valid days: 8
win rate: 5.88%
average net return: -1.0550%
profit factor: 0.1564
decision: ADJUST_AND_RETEST
```

Integrity findings:

- 34 realized trades passed
- 6 records are watch-only or open/unavailable
- 3 reconciled exits lack a trustworthy exit timestamp and are excluded

Remaining work is evidence-link completion, not a new trading tactic:

- persist the pre-Strategist raw Scanner baseline at decision time
- persist explicit Commander selection changes and veto alternatives
- persist `feedback_id -> later_decision_id -> adoption` linkage
- enrich exit MFE/MAE and post-exit checkpoint joins

No remaining item permits a runtime behavior change without a separate
promotion review.

## Evidence Linkage Checkpoint - 2026-06-22

The module and report surfaces above are implemented, but completion of a
surface is not completion of the underlying comparison.

Current attribution state:

- realized full-system performance can be evaluated
- Q8 trusted shadow evidence can be reused
- Scanner A -> Strategist B -> Commander C identity and forward-outcome
  linkage is incomplete
- current attribution outputs correctly remain `UNAVAILABLE`
- Strategist effectiveness therefore remains `INSUFFICIENT_EVIDENCE`

The remaining Q9.3 work is:

1. persist one canonical decision-window snapshot containing A/B/C
2. join A/B/C to trusted Q8, realized, or explicitly reconstructed outcomes
3. backfill only reconstructable historical windows
4. produce bounded attribution decisions by evidence class

This is not a request for another generic observation period. Waiting for more
calendar days without fixing the linkage does not answer the Strategist value
question.

## Start Gate Enforcement - 2026-06-22

Implemented:

- `q9_full_chain_start_gate.v1`
- daily Q8 `CLOSED` and Q9 `READINESS` status
- rolling-window exclusion of pre-Start-Gate days
- explicit required daily decision-window inventory
- reconstructed pre-adjust Scanner Top-10 diagnostics
- rejection of reconstructed rankings as a trusted raw Scanner control
- Monitor entry/exit timeline availability checks
- post-exit checkpoint join into Q9 trade evaluation
- full baseline-version completeness check

Current 2026-06-22 result:

```text
Start Gate: NOT_READY
coverage: 37.5%
formal Q9 forward days: 0
```

Remaining readiness work:

- persist daily decision windows, including no-trade decisions
- persist a true raw Scanner control snapshot
- persist explicit Commander final selection/veto records
- populate Q8, prompt, cost, tactic, policy, and Q9 baseline versions
- ensure every realized exit has joined post-exit evidence

The five-valid-day Q9 clock starts only after these readiness items pass.
