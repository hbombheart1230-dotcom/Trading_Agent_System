# Evaluation Operating Baseline

Date: 2026-06-22

This document is the current authority for Q8/Q9 evaluation status and next
actions. When an older document conflicts with this baseline, this document
and the fixed evaluation contracts take precedence.

## Authority Order

Use documents in this order:

1. `q9_evaluation_contract.md`
2. `current_operating_baseline.md`
3. `q8_closure_lock.md`
4. `q9_full_chain_evaluation_matrix.md`
5. `q8_final_comprehensive_review_2026-06-20.md`
6. `q9_master_plan.md`
7. `q9_implementation_roadmap.md`
8. historical plans and daily reviews under `docs/tactics/`

Historical documents explain why a field or experiment exists. They do not
reopen a completed evaluation window or authorize a behavior change.

## Current Status

| Workstream | Status | Meaning |
| --- | --- | --- |
| Q8 tactical validation | CLOSED | The trusted Q8 window was finalized. Do not restart it because Q9 evidence is incomplete. |
| Q8 shadow collection | CONTINUING AS EVIDENCE | Existing collectors may keep producing tactical counterfactual evidence for Q9. This is not a new Q8 promotion window. |
| Q9 system evaluation | ACTIVE | Q9 evaluates whether the complete decision chain adds value. It remains read-only. |
| Q9 attribution linkage | ACTIVE | New decision windows persist pre-Strategist universe P, Scanner A, Strategist B, and Commander C with forward outcomes. Older windows remain historical context only. |
| Q9 fixed forward window | READY TO START | 2026-06-23 is excluded as the instrumentation/application day. The next full regular-session trading day is Day 1 of the fixed five-valid-day window. |
| Runtime behavior change | PROHIBITED | A separate promotion review is required. |

## Fixed System Scope

Q9 evaluates the existing flow:

```text
Commander
  -> Strategist LLM stages 1-4
  -> Scanner
  -> Monitor
  -> Execution
  -> Report / Memory
```

It does not replace this flow and does not introduce a new trading strategy.

The existing tactic catalog remains the evaluated portfolio:

- playbooks: `breakout`, `pullback`, `reversal`, `defensive`
- tactics:
  - `trend_continuation`
  - `opening_gap_momentum`
  - `opening_range_breakout`
  - `volume_breakout`
  - `vwap_reclaim_pullback`
  - `lower_vwap_rebound_probe`
  - `mean_reversion_probe`
  - `event_theme_momentum`
  - `reversal_reclaim`
  - `cost_aware_scalp`
  - `defensive_observe`
  - `inverse_hedge_reclaim`

Q9 measures this portfolio. It must not invent replacement strategy families
inside the evaluation layer.

## Q8 Conclusion

The final trusted Q8 aggregation covered 2026-06-16 through 2026-06-19:

- raw candidates: 4,557
- deduped candidates: 2,096
- trusted forward observations: 1,802
- trusted forward coverage: 85.97%

Q8 concluded:

- no new tactic was promoted
- broad VWAP reclaim relaxation was rejected
- broad pullback-quality relaxation was rejected
- opening momentum relaxation was rejected
- automatic runner-up substitution remained prohibited
- defensive confirmation concepts were retained
- conditional evidence was handed to Q9

Q8 is therefore complete. Continued Q8 artifact generation is evidence
collection, not an extension of the Q8 decision window.

## Does Q9 Need Shadow Evidence?

Yes, but not as a second generic shadow engine.

Live trades alone are too sparse to answer whether Strategist, Commander, and
Monitor improved candidate selection. Q9 therefore needs counterfactual
evidence at each decision window.

### Required Decision Comparison

For one canonical decision window:

```text
day + decision_epoch + candidate_pool_id
```

Q9 must preserve:

| Label | Decision state |
| --- | --- |
| A | raw Scanner Top-1 before Strategist influence |
| B | candidate/ranking after Strategist influence |
| C | Commander final selection or explicit veto/no-trade |

The later outcome for A, B, and C should reuse trusted Q8 forward observations
when the candidate and baseline timestamp match. If no trustworthy outcome
exists, the comparison remains `UNAVAILABLE`.

### Shadow Types

| Evidence | Purpose | Status |
| --- | --- | --- |
| Q8 tactical shadow | Evaluate blocked candidates, lanes, and missed opportunity | Existing; reuse in Q9 |
| Q9 decision-window counterfactual | Compare Scanner A vs Strategist B vs Commander C | Required linkage; incomplete |
| post-exit shadow | Evaluate Monitor exit timing and profit fade | Existing; continue |
| reconstructed minute path | Fill limited historical gaps with lower confidence | Allowed only as `RECONSTRUCTED` |

The correct implementation is a decision-window link layer, not duplicated
candidate collection.

## Current Implementation Reality

Q9 already has:

- artifact inventory
- trade read model
- broker-truth overlay
- trade evaluator
- daily and rolling scorecards
- attribution schemas
- Strategist and feedback effectiveness report surfaces

Q9 does not yet have enough canonical linkage for:

- raw pre-Strategist Scanner Top-1 forward outcome
- Strategist-selected alternative forward outcome
- Commander selection change or veto alternative outcome
- feedback ID to later decision adoption

The current `counterfactuals.py` correctly leaves these returns and deltas
unavailable. Therefore:

- Q9 may judge realized full-system performance
- Q9 may not yet claim that Strategist beats or loses to Scanner
- waiting for more days without completing the linkage will not solve this gap

Operational enforcement added on 2026-06-22:

- daily scorecards expose Q8 as `CLOSED`
- Q9 remains `READINESS` while the full-chain Start Gate is incomplete
- rolling Q9 forward-window counts exclude pre-gate days
- reconstructed pre-adjust Scanner rankings cannot satisfy the trusted raw
  Scanner control gate
- realized PnL remains visible but cannot be presented as completed Q9
  attribution

Historical loss decomposition added on 2026-06-22:

- realized system performance is materially negative
- Top-pick gross forward edge is below observed round-trip cost
- opening 20-60 minute and late-session candidates show longer-horizon
  conditional strength
- mid-session candidates show negative forward performance
- Monitor exit timing is secondary and cannot repair the current expectancy
  deficit
- first demonstrated repair target is
  `candidate_edge_and_horizon_alignment`

Horizon-alignment review completed on 2026-06-22:

- conservative observed round-trip cost: 0.9991%
- no time/tactic/horizon combination passed the controlled-adoption contract
- `open_20_60m | vwap_reclaim_pullback | +30m` remained observation-only
- its gross +1.0427% became net +0.0436% after cost
- net profit factor was 1.0692 and worst leave-one-day-out return was -0.6807%
- no runtime or policy change was authorized
- the fixed decision is recorded in
  `horizon_alignment_decision_2026-06-22.md`

Full-chain historical component review completed on 2026-06-22:

- Scanner: `ADJUST_AND_RETEST`
- Strategist: `INSUFFICIENT_EVIDENCE`
- Commander: `INSUFFICIENT_EVIDENCE`
- Monitor entry: `RETAIN`
- Monitor exit: `INSUFFICIENT_EVIDENCE`
- full-system positive-edge hypothesis: `REJECT`
- there are no additional diagnostic components to add
- remaining evidence work is limited to trusted A/B/C snapshots and four
  additional post-exit observations
- the fixed component decision is recorded in
  `q9_component_decision_2026-06-22.md`

Q9 A/B/C forward instrumentation added on 2026-06-22:

- one `decision_id` now links Scanner control, Strategist ranking, Commander
  approval/veto, and Q9 forward candidates
- A is a same-candidate-universe Scanner intrinsic ranking control
- B is the post-Strategist ranking and selected candidate
- C is the final approval, rejection, retry, or no-trade decision
- forward candidates are stored separately as `q9_decision_candidates` and
  do not enter Q8 candidate aggregation
- the Scanner control is valid for ranking-effect evaluation only
- Strategist influence on candidate-universe construction remains explicitly
  unavailable
- no trading behavior, guard, prompt, or execution rule changed

## Fixed Next Work

The next work is observability and evidence linkage only.

The complete evaluation scope and fixed five-day protocol are defined in
`q9_full_chain_evaluation_matrix.md`.

### Q9.3A - Decision Snapshot Contract

Persist one canonical record per decision window containing:

- `decision_id`
- `decision_epoch`
- `candidate_pool_id`
- A/B/C symbols, ranks, scores, and reasons
- Strategist scenario and recommendation IDs
- Commander selection, veto, and override reason
- market regime and artifact references

### Q9.3B - Forward Outcome Join

Join A/B/C candidates to:

1. trusted Q8 same-day forward outcomes
2. realized broker outcomes when the candidate was traded
3. reconstructed minute paths only when explicitly labeled

Do not substitute current ranking, report prose, or a different timestamp.

### Q9.3C - Historical Backfill

Backfill only records whose identity and timestamps are reconstructable.
Classify every result as:

- `REALIZED`
- `TRUSTED_SHADOW`
- `RECONSTRUCTED`
- `UNAVAILABLE`

Do not merge these classes into one sample count.

### Q9.3D - Attribution Review

Produce the first bounded answers:

- Scanner A vs Strategist B
- Strategist B vs Commander C
- selected candidate vs no-trade/blocked alternatives

Each review must end with a decision class or a named missing link. It must not
end with an undefined request to observe longer.

### Later Work

After A/B/C attribution works:

1. feedback exposure and adoption linkage
2. exit MFE/MAE and post-exit linkage
3. 5/10/20 valid-day scorecards by evidence class and baseline version
4. promotion review

The historical component review is complete. These items are now forward
instrumentation requirements, not permission to create further evaluation
categories.

## Observation Window Rule

Calendar waiting is not the immediate task.

First complete the full-chain Start Gate and backfill existing evidence.
After that, run one fixed five-valid-day forward window and issue mandatory
component decisions.

The rolling 10/20-day scorecards remain useful monitoring views. They do not
delay the first Q9 component decisions and are not permission for open-ended
evaluation.

A valid day requires the relevant artifacts and comparisons. A day with
missing A/B/C linkage does not become useful merely because time passed.

## Change Control

Until a promotion review approves a change:

- no new entry or exit behavior
- no new tactic
- no guard relaxation
- no Scanner ranking change
- no Commander approval change
- no Strategist prompt change

The immediate objective is to make the existing system measurable, not to
continue patching trading behavior.
