# Q8-Q17 Cumulative Review Addendum

Date: 2026-07-27

## Purpose

Re-read accumulated Q8-Q17 evidence without adding another evaluation axis or
changing live behavior. The goal is to extract reusable evidence and leave one
clear decision surface for the end of Q17.

## Implemented Observability

1. Q14 causal interpretation

   `Scanner Ranking Failure` and `Aligned / No Alignment Issue` are now
   explicitly identified as outcome-conditioned labels. They remain in the
   frozen report, but cannot independently prove a Scanner defect.

2. Episode-level Scanner review

   Repeated candidate snapshots are compressed by trading day, symbol, setup,
   and a 15-minute gap. Top-1 and lower-rank forward outcomes can therefore be
   compared without treating every repeated minute as an independent sample.

3. Same-symbol reentry review

   Closed trades are split into the first same-day/same-symbol entry and later
   reentries. This is observational and does not install a cooldown.

4. Confirmed post-reclaim shadow review

   `post_reclaim_pullback_candidate` is evaluated separately at 5, 15, 30, and
   60 minutes. Gross, estimated live-cost net, and mock-cost net results are
   kept separate.

5. Scanner score component preservation

   New Q9 snapshots preserve available `source_scores`, `score_breakdown`,
   chart-fit, quant-factor, and cost-filter fields. Historical missing
   components are not backfilled with inferred values.

6. Unified cumulative report

   One report combines the evidence above with Strategist B versus Scanner A
   paired outcomes and current Q14 classification.

## Decision Rules

- Q17 remains the active fixed validation.
- This work is evaluation-only.
- No candidate is promoted during Q17.
- Missing historical evidence is reported, not scored as failure.
- Mock and estimated live costs must never be mixed in one expectancy.
- Repeated windows and independent episodes must never be presented as the
  same sample count.
- After Q17, select at most one behavior patch and compare it with the same
  frozen Q13/Q14/Q17 measurements.

## Candidate Classes

The cumulative review can surface:

- same-symbol loss reentry control
- confirmed post-reclaim pullback subtype
- Scanner rank-ordering component review
- Strategist ranking-weight guard

These are candidates, not policies. Eligibility requires adequate evidence and
does not override the Q17 freeze.

## Acceptance Checks

- Q14 legacy labels remain available.
- Structural and outcome-conditioned Q14 findings are visibly separated.
- Episode compression is deterministic.
- Cost assumptions are explicit.
- New score components survive Q9 snapshot and shadow artifact generation.
- The cumulative report regenerates from retained artifacts alone.
- Existing Q9/Q13/Q14 tests continue to pass.
