# Q8 Shadow Evaluation Operating Plan

Status: Q8 PROMOTION WINDOW CLOSED / COLLECTOR RETAINED

This methodology remains valid for interpreting Q8 shadow artifacts, but it
does not reopen Q8. Existing shadow data now serves as a lower-layer evidence
source for Q9. Q9 decision-window comparisons must reuse this evidence rather
than create a duplicate generic shadow engine. See
`../evaluation/current_operating_baseline.md`.

Purpose: define how to evaluate Q8 shadow data after each live trading day and
how to decide what becomes a promotion candidate.

This document is evaluation methodology only. It does not change runtime
behavior, entry logic, exit logic, scanner ranking, monitor rules, Strategist
prompts, or broker execution.

## Daily Review Goal

After each trading day, answer:

- What did Q8 block?
- Were the blocks correct?
- Which blocks preserved capital?
- Which blocks created missed opportunity?
- Which signals should remain under observation?
- Which signals should become promotion candidates?

## Required Inputs

- quant shadow candidate files
- trade lifecycle bundles
- broker truth snapshots
- operator summary
- macro indicator snapshots
- post-exit shadow observations
- trade reports where available

## Review Sequence

1. Confirm artifact integrity.
2. Count live trades and shadow candidates.
3. Group shadow candidates by blocker/reason.
4. Compare blocked candidates against later same-symbol outcomes.
5. Compare selected candidate against Scanner Top-1 and runner-ups.
6. Identify correct blocks.
7. Identify missed opportunities.
8. Assign promotion decision class.
9. Document next-day observation targets.

## Core Metrics

| Metric | Meaning |
| --- | --- |
| Candidate count | total candidates captured in shadow |
| Raw candidate count | total rows before duplicate collapse |
| Deduped candidate count | rows after `day + symbol + baseline_epoch + entry_lane_subtype` collapse |
| Duplicate count | raw minus deduped rows, used to avoid overstating repeated same-window observations |
| Trusted forward count | deduped candidates with same-day, near-target forward checkpoints |
| Trusted forward coverage | trusted forward count divided by deduped candidate count |
| Evaluated count | candidates with enough fields to evaluate |
| Would-enter count | candidates that would have entered under current evaluation |
| Blocker count | count by blocker/reason |
| Average forward return | later return from baseline price |
| Max favorable move | largest later upside after observation |
| Max adverse move | largest later downside after observation |
| Missed opportunity count | blocked candidates with meaningful later upside |
| Correct block count | blocked candidates that later declined or failed |
| Opportunity cost | aggregate upside missed by blocked candidates |

## Trusted Forward Gate

Q8 promotion decisions must use trusted forward outcomes only.

Trusted forward requirements:

- the forward checkpoint must be from the same trading day as the baseline
- the observed row must be close to the requested checkpoint target
- cross-day observations are marked `stale_cross_day_observation`
- same-day but delayed observations are marked `stale_forward_gap`
- stale checkpoints are not counted as observed outcomes
- repeated rows are deduped before averaging performance

Daily summaries should expose:

```text
Q8 Evaluation Trust Gate
- raw candidate count
- deduped candidate count
- duplicate rate
- trusted forward count
- trusted forward coverage
- promotion_allowed
- block reasons
```

Promotion is blocked according to `q8_evaluation_contract.md` when:

- trusted forward count is below 100
- trusted forward coverage is below 70%
- duplicate rate is above 75%
- no candidate has repeatable evidence across at least 2 observed days

This gate exists to prevent stale or duplicated shadow evidence from creating
false promotion candidates.

## Blocker Review Template

| Blocker / Reason | Count | Avg Later Return | Max Favorable Move | Correct Blocks | Missed Opportunities | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
|  |  |  |  |  |  |  |

Decision values:

- `retain_under_observation`
- `adjust_and_retest`
- `promotion_candidate`
- `reject_candidate`

## Current 2026-06-02 Midday Observation

This is a live intraday observation, not a final daily scorecard.

Early evidence suggests:

- `volume_confirmation_missing` preserved capital in many cases.
- `vwap_pullback_promoted_quality_gate` has not shown strong missed
  opportunity so far.
- `breakout_not_ready` may be too conservative.
- `pullback_not_mature` may be too conservative in some conditions.
- `human_chart_sanity_guard_blocked` may be blocking high-quality opportunities.
- market regime context is not yet formally attached to the Q8 evaluation.

Initial decision framing:

| Signal | Current Status | Next Action |
| --- | --- | --- |
| Cost edge / cost floor | retain under observation | keep measuring blocked candidate outcomes |
| Volume confirmation | retain under observation | keep measuring missed opportunity rate |
| VWAP pullback promoted quality gate | retain under observation | keep measuring by regime |
| Breakout readiness | adjust-and-retest candidate | review after full-day data |
| Pullback maturity | adjust-and-retest candidate | review after full-day data |
| Human chart sanity guard | promotion-candidate review target | inspect blocked winners and failure modes |
| Market regime rail | new observation layer | document and attach as shadow-only first |
| News event intelligence | new observation layer | attach event/theme/symbol watch evidence as shadow-only first |

## Promotion Candidate Rule

A Q8 signal becomes a promotion candidate only if:

- artifact integrity is acceptable
- sample size is sufficient
- trusted forward gate allows promotion review
- candidate evidence is deduped
- candidate evidence appears across at least 2 observed days
- baseline comparison is available
- benefit or harm is measurable
- opportunity cost is documented
- the proposed change is scoped and reversible

Do not promote from one attractive example.

## End-of-Day Output

Each trading day should produce a short review:

```text
Date:
Live trades:
Shadow candidate files:
Evaluated candidates:
Would-enter candidates:
Top correct blockers:
Top missed-opportunity blockers:
Signals to retain:
Signals to adjust and re-test:
New observation layers:
Critical defects:
Next-day observation targets:
```

News event intelligence review addendum:

```text
News event candidates:
Theme watch candidates:
Symbol watch candidates:
Strategist usage status:
Linked symbols that passed scanner:
Linked symbols blocked by monitor/cost/volume:
Linked symbols that became missed opportunities:
False-positive news event links:
Next-day news event observation targets:
```

## 2026-06-02 Review Focus

For today's close, focus on:

- whether 061040 lifecycle, broker truth, and report truth align
- whether blocked 035420 and 004540 opportunities were real missed entries
- whether Samsung Electronics / SK Hynix blocks were correct
- whether breakout readiness blocked winners
- whether human chart sanity blocked winners
- whether macro regime should have shifted evaluation toward relative-strength
  breakout/reclaim instead of normal pullback logic

## 2026-06-02 Close Review Result

Detailed review:

- `q8_daily_review_2026-06-02.md`

Artifact status:

- Initial broker/lifecycle/report mismatch was found and repaired.
- Broker order/fill reconciliation is now aligned.
- `ka10170` day trade diary shows `061040` fully closed.
- Daily report integrity shows `broker_closed_report_open_count=0`.

Q8 status under the original 2026-06-02 review:

| Surface | Status | Decision |
| --- | --- | --- |
| Live closed-trade sample | `hold_sample_insufficient` | no strategy promotion |
| Shadow dataset | `legacy_ready` | observation-only unless regenerated under `q8_evaluation_contract.md` |
| Cost edge | active hard gate | retain official policy |
| VWAP pullback quality gate | active hard gate | retain and monitor opportunity cost |
| Volume confirmation | observation | retain under observation |
| Pullback maturity | review | legacy review target, not promotion evidence |
| Breakout readiness | review | legacy review target, not promotion evidence |
| Human chart sanity | review | legacy review target, not promotion evidence |
| Market regime rail | observation-only | attach to Q8 evidence later |
| News event intelligence | observation-only | compare linked symbols against unlinked scanner candidates |
| Long horizon | observation-only | no unlock |

Next live validation day target:

- Do not optimize strategy before confirming artifact integrity after close.
- Use the next session to compare blocked breakout-like candidates, human chart
  sanity blocks, and pullback maturity blocks against forward outcomes.
- Keep market regime rail as observation-only until it is attached to
  Strategist interpretation and Q8/shadow outcomes.
- Keep news event intelligence as observation-only until event/theme/symbol
  watch candidates can be compared against forward outcomes and raw scanner
  candidates.

## Boundary

Q8 shadow review may recommend promotion candidates. It must not directly
change:

- entry rules
- exit rules
- guard thresholds
- scanner ranking
- Strategist prompts
- order sizing
- broker execution
