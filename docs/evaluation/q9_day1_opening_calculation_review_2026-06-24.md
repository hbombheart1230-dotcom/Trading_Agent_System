# Q9 Day 1 Opening Calculation Review - 2026-06-24

## Status

- Review date: 2026-06-24
- Evaluation window: Q9 fixed five-valid-day window, Day 1
- Scope: Samsung Electronics (`005930`) and SK hynix (`000660`) opening move
- Behavior effect: none
- Runtime policy change: prohibited during the freeze

This review records a calculation and model-fit diagnosis. It does not authorize
entry, exit, Scanner, Strategist, Commander, or Monitor changes.

## Observed Market Move

| Symbol | Open | Observed high | High vs open | Last reviewed price | Last vs open |
|---|---:|---:|---:|---:|---:|
| `005930` | 314,000 | 337,000 | +7.325% | 335,500 | +6.847% |
| `000660` | 2,598,000 | 2,689,000 | +3.503% | 2,681,000 | +3.195% |

The system produced no opening entry despite these material upward moves.

## Finding

The implementation performed the configured arithmetic, but that does not prove
that the calculation model was appropriate for detecting an opening rebound.

Current verdict:

> Arithmetic implementation is internally consistent. The opening-rebound
> interpretation is not yet validated and shows material model-fit concerns.

This is not classified as a simple arithmetic bug. It is a possible mismatch
between the selected reference windows, state labels, and the intended opening
momentum question.

## 1. Volume Confirmation

Current implementation:

```text
raw volume ratio = current 1-minute volume / average volume of prior N bars
```

The default lookback is five prior bars. During the opening window, the code may
replace the average-based ratio with a median-based ratio only when all of the
following hold:

- the average is sufficiently skewed by one large bar;
- the maximum reference volume is sufficiently larger than the median;
- the raw ratio is at least `max(0.30, threshold * 0.50)`;
- the median-based ratio meets the configured threshold.

Observed opening ratios included approximately:

- `000660`: `0.067`, `0.135`, `0.250`
- `005930`: `0.057`, later approximately `0.421`

The opening auction or first high-volume bar can remain in the denominator and
make subsequent strong price bars appear volume-weak. The median adjustment
cannot activate when the raw-ratio floor is below `0.30`.

Assessment:

- The division itself is correct.
- The reference-window design can understate continuation volume immediately
  after an exceptional opening bar.
- Therefore `volume_ratio_below_*_floor` is not sufficient evidence that the
  observed price move lacked meaningful market participation.

## 2. Cost-Edge State

The cost filter calculates:

```text
cost-adjusted edge = estimated gross edge - effective cost drag
```

However, observed rows had:

- `cost_floor_state = not_met`
- `cost_adjusted_edge_pct = null`

This means an estimated gross directional edge was unavailable. It does not mean
that a numeric expected return was calculated and found smaller than costs.

The current output can therefore combine two materially different states:

1. numeric edge exists but does not exceed the required cost threshold;
2. numeric edge cannot be calculated because directional evidence is absent.

Assessment:

- Fee and tax arithmetic is internally consistent.
- The `not_met` label is semantically too broad for diagnosis.
- Day 1 blockers must not be interpreted as proven negative expected value when
  `cost_adjusted_edge_pct` is null.

The configured conservative floor also matters:

- estimated transaction cost drag: approximately `0.21%`
- policy round-trip cost floor: `0.90%`
- required gross edge can reach approximately `1.65%` after multiplier and
  profit buffer application

This may be intentional risk policy, but it is not equivalent to actual broker
cost.

## 3. Opening Large-Cap Surge Shadow

The observation-only large-cap opening probe requires all of the following:

- symbol is `005930`, `000660`, or `009150`;
- no more than 20 minutes have passed since market open;
- cost edge passes;
- volume ratio is at least `0.72`;
- price is not below VWAP;
- breakout, weighted score, or human chart structure passes.

This is a conjunctive gate. Failure of any one condition results in
`would_probe = false`.

Assessment:

- The boolean evaluation matches the implementation.
- It is not proven that this conjunction is a correct detector for sharp
  post-selloff opening rebounds.
- A large realized price move does not itself prove that entry was safe, but it
  proves that "no opportunity existed" would be an unsupported conclusion.

## 4. VWAP Interpretation

Session VWAP is volume-weighted and can be dominated by the opening auction or
first high-volume bar. A stock can remain below session VWAP while still showing
a material rebound relative to the open or previous close.

Assessment:

- VWAP arithmetic is not currently identified as defective.
- `below_vwap` answers a different question from "is the stock recovering
  strongly from the opening level?"
- Treating the two questions as equivalent can reject valid rebound structures.

## Q9 Attribution

For Day 1 reporting, classify this observation as:

```text
calculation_status: IMPLEMENTATION_CONSISTENT
model_fit_status: NOT_VALIDATED_FOR_OPENING_REBOUND
primary_concerns:
  - opening_volume_reference_distortion
  - missing_edge_evidence_reported_as_cost_failure
  - conjunctive_opening_gate_strictness
  - vwap_rebound_question_mismatch
```

Do not classify it as:

- confirmed good block;
- confirmed missed profitable trade;
- Scanner failure without full P/A/B/C comparison;
- Monitor failure without forward-risk and drawdown analysis;
- evidence authorizing opening-rule relaxation.

## Required Evidence During The Freeze

For each opening decision window, preserve:

- current one-minute volume;
- all reference-bar volumes;
- average and median reference volume;
- raw and effective volume ratios;
- whether median adjustment was attempted and why it passed or failed;
- current price, open, previous close, VWAP, and distances from each;
- estimated gross edge and its source;
- effective cost drag and required gross edge;
- explicit distinction between `EDGE_UNAVAILABLE` and `EDGE_BELOW_COST`;
- each opening-gate condition as an independent boolean;
- 5-minute, 15-minute, 30-minute, and EOD forward returns;
- MFE and MAE where available.

## Frozen-Window Decision

No behavior patch is authorized from this single observation.

At the end of the fixed five-day window:

1. compare price moves rejected only by distorted opening volume with moves that
   had genuinely weak volume;
2. separate missing edge evidence from numeric cost-edge failure;
3. compare below-VWAP rebounds with true below-VWAP failures;
4. calculate whether the full conjunction improves risk-adjusted outcomes over
   each condition independently;
5. decide `RETAIN`, `ADJUST AND RE-TEST`, or `REJECT` through the promotion
   framework.

