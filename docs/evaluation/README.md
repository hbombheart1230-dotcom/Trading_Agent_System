# Q9 Evaluation Layer

This folder owns the post-Q8 evaluation layer.

## Current Authority

Read `current_operating_baseline.md` first.

Current status as of 2026-06-23:

- Q8 tactical validation is closed.
- Existing Q8 shadow collectors may continue as Q9 evidence providers.
- Q9 read-only system evaluation is active.
- Q9 P/A/B/C decision-window instrumentation is implemented.
- 2026-06-23 is an instrumentation/application day and is excluded from the
  formal sample.
- The next full regular-session trading day is Day 1 of the fixed five-valid-
  trading-day forward window.
- No runtime behavior change is authorized.

Q8 answers:

> Did a specific tactical gate or entry lane behave as expected?

Q9 answers:

> Did the complete decision system create measurable trading value?

Q9 evaluates Commander, Strategist, Scanner, Monitor, execution, Reporter
feedback, and their interactions. It does not create a new trading tactic and
does not replace Q8.

## Fixed Program Names

- Q9: `Multi-Agent Attribution Evaluation`
- Q10: `Samsung/Hynix Large-Cap Baseline Control`
- Q11: `Opening Surge & Market Reversal Research` (`09:00-10:00 KST`)

Q10 and Q11 are independent shadow programs running in parallel with Q9. They
are not sequential replacements for Q9.

## Documents

- `current_operating_baseline.md`
  - current Q8/Q9 authority and status
  - fixed meaning of Q8 shadow vs Q9 counterfactual evidence
  - bounded next work and observation windows
- `q9_fixed_forward_window_protocol_2026-06-23.md`
  - fixed five-trading-day freeze boundary
  - permitted measurement-only fixes
  - mandatory daily post-close checks
  - valid-day and sample-count rules
- `q9_day1_opening_calculation_review_2026-06-24.md`
- `q9_horizon_contract_observability_2026-06-26.md`
  - adds read-only Strategist/Commander intended holding-window attribution
  - records premature exits versus strategy horizon without changing runtime
  - Day 1 Samsung Electronics and SK hynix opening-move diagnosis
  - separates arithmetic correctness from opening-model fitness
  - records volume-reference, cost-edge-state, VWAP, and compound-gate concerns
  - authorizes no runtime behavior change during the freeze
- `opportunity_engine_shadow_plan.md`
  - Q11 independent 09:00-10:00 opening-surge and market-reversal research
  - records real-time market, breadth, relative-strength, volume, and turnover evidence
  - produces virtual probe entries and exits without Q9 or runtime integration
- `baseline_samsung_hynix_control.md`
  - Q10 independent Samsung Electronics / SK hynix large-cap control
  - compares a fixed-universe rule baseline against Q9 without changing Q9
- `q9_full_chain_evaluation_matrix.md`
  - fixed Strategist, Scanner, Commander, Monitor-entry, and Monitor-exit scope
  - Top-10 evaluation boundary and rank-bucket comparisons
  - Q9 Start Gate and non-extendable five-valid-day forward window
- `q8_closure_lock.md`
  - permanent Q8 closure boundary
  - opening-overshoot and other future research separation rule
  - explicit prohibition on reopening Q8 from Q9 evidence gaps
- `loss_decomposition_decision_2026-06-22.md`
  - first historical candidate -> ranking -> entry -> exit loss decomposition
  - fixes candidate edge and horizon alignment as the first demonstrated loss
    source
  - records why exit tuning is not the first repair target
- `q8_handoff_2026-06-19.md`
  - closes the current Q8 validation window
  - records which candidates were rejected or retained
  - defines which Q8 artifacts Q9 may reuse
- `q8_final_comprehensive_review_2026-06-20.md`
  - records the final trusted reaggregation
  - separates retained policies, rejected relaxations, Q9 research questions,
    and the broker cost-profile defect
- `q9_master_plan.md`
  - target architecture
  - business questions
  - evaluation workflow
  - required outputs
- `q9_evaluation_contract.md`
  - fixed truth hierarchy
  - comparison units
  - sample and confidence rules
  - decision classes and change control
- `q9_implementation_roadmap.md`
  - phases and slices
  - module boundaries
  - verification plan
  - completion criteria

## Evaluation Flow

```text
Q8 Tactical Evidence
  + Broker Truth
  + Lifecycle / Report Truth
  + Scanner Candidate Snapshots
  + Strategist Decisions
  + Monitor Entry / Exit Decisions
  + Shadow / Post-Exit Outcomes
              |
              v
       Trade Read Model
              |
              v
        Trade Evaluator
              |
              v
        Daily Scorecard
              |
       +------+------+
       |             |
       v             v
Strategist       Feedback
Effectiveness    Effectiveness
       |             |
       +------+------+
              v
       Promotion Review
```

## Hard Boundary

Q9 is read-only until a separate promotion review is approved.

Q9 must not directly change:

- entry or exit eligibility
- tactic selection
- Scanner ranking
- Monitor thresholds
- Commander approval
- position sizing
- Strategist prompts
- feedback injection
- order placement

## Operating Principle

Q9 does not wait indefinitely for perfect live-trade samples.

## Running The Evaluation

```powershell
venv\Scripts\python.exe scripts\run_q9_evaluation.py --date YYYY-MM-DD --reports-root reports
```

Generated outputs are written only below:

```text
reports/evaluation/
```

The command does not import or modify Commander, Strategist, Scanner, Monitor,
or execution behavior.

## Implementation Status

As of 2026-06-19:

- artifact inventory is implemented
- Q9 trade read model and broker-truth exit overlay are implemented
- trade evaluation is implemented
- Scanner/Strategist/Commander attribution records are implemented
- daily and 5/10/20-day rolling scorecards are implemented
- Strategist and feedback effectiveness surfaces are implemented
- the latest 10 artifact-bearing trading days were backfilled

The current Q9 instrumentation persists:

- Scanner pre-Strategist source universe and intrinsic Top-20
- Scanner control A
- Strategist-ranked B
- Commander final C
- Top-1/3/5/10 forward outcomes
- source-level forward outcomes

Historical days without these additive fields remain unavailable rather than
being inferred. Feedback ID to later decision adoption linkage is still a
future comparison.

Unavailable comparisons must remain unavailable. They must not be inferred
from current rank or narrative text.

Q9 is designed to combine:

- realized broker-truth trades
- trusted Q8 shadow outcomes
- Scanner-vs-selected counterfactuals once decision-window links exist
- post-exit outcomes
- integrity confidence

New forward windows link P/A/B/C records to later outcomes. Older records that
predate the instrumentation remain historical context only.

Every result must state whether it is:

- realized evidence
- trusted shadow evidence
- reconstructed counterfactual evidence
- insufficient evidence
