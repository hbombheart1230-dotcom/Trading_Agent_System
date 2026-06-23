# Q9 Evaluation Layer

This folder owns the post-Q8 evaluation layer.

## Current Authority

Read `current_operating_baseline.md` first.

Current status as of 2026-06-22:

- Q8 tactical validation is closed.
- Existing Q8 shadow collectors may continue as Q9 evidence providers.
- Q9 read-only system evaluation is active.
- Q9 decision-window attribution linkage is incomplete.
- The formal five-day Q9 forward window has not started because the full-chain
  Start Gate does not yet pass.
- No runtime behavior change is authorized.

Q8 answers:

> Did a specific tactical gate or entry lane behave as expected?

Q9 answers:

> Did the complete decision system create measurable trading value?

Q9 evaluates Commander, Strategist, Scanner, Monitor, execution, Reporter
feedback, and their interactions. It does not create a new trading tactic and
does not replace Q8.

## Documents

- `current_operating_baseline.md`
  - current Q8/Q9 authority and status
  - fixed meaning of Q8 shadow vs Q9 counterfactual evidence
  - bounded next work and observation windows
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

The following comparisons remain explicitly unavailable until their canonical
links exist:

- raw Scanner Top-1 forward outcome before Strategist influence
- Commander alternative outcome when it changes or vetoes selection
- feedback ID to later decision adoption linkage

Unavailable comparisons must remain unavailable. They must not be inferred
from current rank or narrative text.

Q9 is designed to combine:

- realized broker-truth trades
- trusted Q8 shadow outcomes
- Scanner-vs-selected counterfactuals once decision-window links exist
- post-exit outcomes
- integrity confidence

The first, second, and fourth evidence sources exist. Scanner/Strategist/
Commander alternative outcomes remain unavailable until canonical A/B/C
decision-window records are linked to later outcomes.

Every result must state whether it is:

- realized evidence
- trusted shadow evidence
- reconstructed counterfactual evidence
- insufficient evidence
