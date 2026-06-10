# Q8 Shadow Evaluation Operating Plan

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
| Deduped candidate count | rows after `symbol + reason + shadow_role + baseline_epoch + tactic_id` collapse |
| Duplicate count | raw minus deduped rows, used to avoid overstating repeated same-window observations |
| Evaluated count | candidates with enough fields to evaluate |
| Would-enter count | candidates that would have entered under current evaluation |
| Blocker count | count by blocker/reason |
| Average forward return | later return from baseline price |
| Max favorable move | largest later upside after observation |
| Max adverse move | largest later downside after observation |
| Missed opportunity count | blocked candidates with meaningful later upside |
| Correct block count | blocked candidates that later declined or failed |
| Opportunity cost | aggregate upside missed by blocked candidates |

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

Q8 status:

| Surface | Status | Decision |
| --- | --- | --- |
| Live closed-trade sample | `hold_sample_insufficient` | no strategy promotion |
| Shadow dataset | `ready` | valid for pre-entry guard and missed-opportunity review |
| Cost edge | active hard gate | retain official policy |
| VWAP pullback quality gate | active hard gate | retain and monitor opportunity cost |
| Volume confirmation | observation | retain under observation |
| Pullback maturity | review | adjust-and-retest candidate |
| Breakout readiness | review | adjust-and-retest candidate |
| Human chart sanity | review | promotion review target |
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
