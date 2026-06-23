# Q9 Evaluation Contract

This contract fixes the Q9 evaluation rules.

Changing this contract requires explicit operator approval, matching tests, and
a version increment.

## Contract Version

```text
q9_evaluation_contract.v1
```

## Evidence Classes

| Class | Meaning | Allowed Use |
| --- | --- | --- |
| `REALIZED` | broker-reconciled executed trade | performance and policy review |
| `TRUSTED_SHADOW` | Q8 deduped same-day forward outcome | selection and opportunity-cost review |
| `RECONSTRUCTED` | historical path reconstructed without full decision snapshot | diagnostic support only |
| `UNAVAILABLE` | evidence cannot be reconstructed safely | missing-data report only |

No metric may combine evidence classes without separate counts.

## Integrity Gate

Status classes:

- `PASS`
- `WATCH`
- `FAIL`
- `BLOCKER`

Rules:

- `BLOCKER` trades are excluded from performance evaluation.
- `FAIL` trades may appear in diagnostics but not promotion metrics.
- `WATCH` trades must report the affected fields.
- `PASS` trades may be used in all Q9 calculations.

Automatic blockers:

- broker closed but lifecycle open
- broker quantity conflicts with lifecycle quantity
- realized PnL source missing or contradictory
- duplicate lifecycle identity
- entry or exit cannot be ordered chronologically

## Metric Basis

Realized performance uses:

```text
broker-truth net return after fee and tax
```

Shadow performance uses:

```text
baseline minute price to trusted checkpoint return
```

The two values must never be presented as the same metric.

## Scanner vs Strategist Comparison

Required comparison:

```text
A: Scanner Top-1 candidate at the decision window
B: Final candidate after Strategist influence
C: Final candidate after Commander intervention
```

Outputs:

- `strategist_delta = B - A`
- `commander_delta = C - B`
- `system_delta = C - A`

If A, B, or C lacks trusted evidence, the relevant delta is `unavailable`.

## Monitor Entry Comparison

For entered trades:

- realized entry vs earliest trusted eligible entry
- realized entry vs selected-candidate baseline
- immediate MAE
- later MFE

For blocked trades:

- blocked baseline vs +5/+15/+30 minute trusted outcome
- correct block, missed opportunity, or ambiguous

## Exit Comparison

Required metrics:

- realized net return
- maximum favorable excursion before exit
- maximum adverse excursion before exit
- captured MFE ratio
- peak-to-exit fade
- post-exit +5/+15/+30/+60 minute return

Exit labels:

- `good_risk_exit`
- `good_profit_capture`
- `early_exit`
- `late_exit`
- `forced_closeout`
- `ambiguous`

## Minimum Evidence

### Daily descriptive output

No minimum sample. It must display the sample count.

### Directional finding

Minimum:

- 20 comparable realized or trusted observations
- at least 2 valid trading days
- integrity coverage at least 90%

### Promotion candidate

Minimum:

- 50 comparable observations
- at least 3 valid trading days
- integrity coverage at least 95%
- positive effect after costs
- no single day contributes more than 60% of observations
- no unresolved `BLOCKER`

### Strong policy decision

Minimum:

- 100 comparable observations
- at least 5 valid trading days
- at least 2 market-regime groups where applicable
- effect remains directionally consistent

Sparse realized trades may be supplemented with trusted shadow evidence, but
the evidence classes and counts must remain separate.

## Effect Thresholds

Q9 does not declare value from a statistically positive but economically
trivial result.

Default economic materiality:

- net expectancy improvement greater than estimated round-trip cost
- or meaningful drawdown reduction without excessive opportunity loss
- or meaningful profit-fade reduction

Every review must report:

- absolute delta
- relative delta
- cost-adjusted delta
- confidence
- sample concentration

## Confidence

| Confidence | Conditions |
| --- | --- |
| `high` | clean integrity, sufficient sample, multi-day consistency |
| `medium` | usable evidence with limited sample or regime concentration |
| `low` | reconstructed evidence, sparse sample, or meaningful missing fields |
| `none` | unavailable or blocked evidence |

## Decision Classes

- `RETAIN`
- `PROMOTION_CANDIDATE`
- `ADJUST_AND_RETEST`
- `REJECT`
- `DEPRECATE_CANDIDATE`
- `INSUFFICIENT_EVIDENCE`

Q9 may assign a decision class. It may not apply the decision to runtime.

## No Endless Evaluation Rule

Every review window must end with one of:

- a decision class
- a named missing artifact defect
- a named comparison that cannot currently be constructed

The system must not extend an evaluation merely because results are mixed.
Mixed evidence with sufficient sample becomes:

```text
RETAIN
ADJUST_AND_RETEST
or REJECT
```

`INSUFFICIENT_EVIDENCE` is allowed only when a stated minimum is not met.

## Baseline Freeze

Each scorecard records:

- active policy hash
- Strategist prompt/version reference
- tactic contract version
- Q8 contract version
- Q9 contract version
- cost model version

Results from different baselines must be grouped separately unless an explicit
bridge analysis is produced.

## Change Control

Changing any of the following requires contract versioning:

- truth hierarchy
- comparison unit
- dedupe key
- evidence class
- minimum sample
- integrity gate
- effect threshold
- decision class

