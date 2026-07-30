# Q18 Post-Reclaim Pullback Promotion Review

Date: 2026-07-30

Status: `CLOSED_RETAIN_SHADOW`

Final decision:

- `q18_close_decision_2026-07-30.md`

The historical episode reconstruction exposed a missing per-episode forward
artifact. Q18 therefore closed immediately under its fixed evidence rules and
did not start the optional five-day extension.

## Definition

Q18 is the final bounded promotion review for:

`vwap_reclaim:confirmed_post_reclaim_pullback`

Q18 is not:

- a new attribution axis
- a replacement for Q8-Q17
- a broad VWAP or pullback relaxation
- an open-ended live validation program
- a change to Scanner, Strategist, Commander, Monitor, exit, or execution

Q18 reuses frozen Q8-Q17 evidence and applies the existing Promotion Framework
to one shadow candidate.

## Current Prior

The pre-episode aggregate contains:

- 27 candidates
- 26 observed candidates
- 14 observed days
- 96.3% forward coverage
- +15m live-net expectancy: +0.1555%
- +30m live-net expectancy: +0.2447%
- +60m live-net expectancy: +0.2135%

These rows are not yet promotion-quality independent samples. Same-symbol and
adjacent-time observations may be serially correlated.

## Fixed Duration

Q18 starts with immediate historical episode reaggregation.

1. If the historical episode dataset meets every evidence gate, decide
   immediately without waiting for another trading day.
2. If it does not meet every evidence gate, collect at most five additional
   full trading days.
3. Close Q18 at the earlier of:
   - all gates becoming decision-ready
   - the fifth additional full trading day closing
4. Do not extend Q18.

If no new qualifying setup occurs during the five-day window, close as
`RETAIN SHADOW`. Lack of events does not authorize a broad entry relaxation.

## Independent Episode Rule

Use a 15-minute episode gap.

- same day
- same symbol
- same confirmed subtype
- observations less than 15 minutes apart

These observations form one episode. Use the first qualifying observation as
the episode entry reference. Do not select the best observation after seeing
the forward outcome.

Different symbols are separate episodes. The same symbol can form a new
episode only after a gap of at least 15 minutes.

## Evidence Gates

All evidence gates are fixed before reviewing the episode outcomes.

| Gate | Requirement |
| --- | --- |
| Independent episodes | at least 20 |
| Observed trading days | at least 10 |
| Distinct symbols | at least 5 |
| Forward coverage | at least 90% |
| Largest single-day share | no more than 30% |
| Largest single-symbol share | no more than 40% |
| Artifact integrity | no unresolved synthetic, schema, symbol, or price issue |

Failure to meet an evidence gate does not produce `REJECT` by itself. It
produces `RETAIN SHADOW` at the fixed deadline.

## Performance Gates

Use the 0.28% live-deployment equity cost assumption, including slippage.
Keep the mock-observed 1.086849% result visible but do not use it as the primary
promotion basis for a future real-account policy.

All performance gates must pass:

| Metric | Requirement |
| --- | --- |
| +15m live-net expectancy | greater than 0 |
| +30m live-net expectancy | greater than 0 |
| +30m profit factor | at least 1.20 |
| Positive-day ratio at +30m | at least 60% |
| +30m episode cumulative MDD | no worse than -6.0% |
| Baseline comparison | better than the same-window Scanner Rank 1 live-net result |

The +30m horizon is primary. The +15m horizon verifies that the edge is not
created only by a late outlier. The +60m horizon is diagnostic and cannot
override failed +15m or +30m gates.

## Decision Classes

### PROMOTE

Requirements:

- every evidence gate passes
- every performance gate passes
- no unresolved integrity issue

Next action:

- implement only the confirmed subtype as controlled adoption
- preserve all unrelated Q15/Q16 guards
- use small bounded sizing
- define rollback before enabling execution

### RETAIN SHADOW

Use when:

- the fixed deadline arrives with insufficient independent evidence
- expectancy remains positive but one robustness gate is not met
- concentration or baseline comparison remains unresolved

Next action:

- keep collecting through normal runtime
- do not start another numbered evaluation phase
- do not relax broad VWAP or pullback rules

### REJECT

Use when decision-ready evidence shows any of:

- +30m live-net expectancy is not positive
- +30m profit factor is at most 1.0
- positive performance is explained by one dominant day or symbol
- the candidate does not outperform same-window Scanner Rank 1
- an integrity defect invalidates the claimed edge and clean reconstruction
  is impossible

Next action:

- remove the candidate from promotion consideration
- retain its artifact fields only for historical compatibility

## Required Output

Generate one final review:

`reports/evaluation/reviews/q18_post_reclaim_promotion_review.md`

The report must contain:

- raw observations and independent episode count
- day and symbol concentration
- +5m/+15m/+30m/+60m gross, live-net, and mock-net results
- win rate, average gain, average loss, profit factor, and MDD
- same-window Scanner Rank 1 comparison
- evidence-gate table
- performance-gate table
- one final decision: `PROMOTE`, `RETAIN SHADOW`, or `REJECT`

## Closure Boundary

Q18 ends with one promotion decision. It does not create Q19 automatically.

If Q18 returns `PROMOTE`, controlled adoption is an implementation task with a
predefined rollback check. If Q18 returns `RETAIN SHADOW` or `REJECT`, the
evaluation program remains closed.
