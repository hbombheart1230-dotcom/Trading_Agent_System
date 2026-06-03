# Intraday Validation Checklist

Purpose: validate the existing Q8/tactics evidence layer during live trading.

This checklist does not authorize execution, entry, exit, strategy, guard, or
approval-flow changes. Any behavior change must be handled separately after
validation evidence is reviewed.

## Required Artifacts

For every live trade day, confirm that these artifacts are generated and
populated:

- trade lifecycle bundle
- trade report
- operator summary
- quant tactic outputs
- entry quant decision
- exit quant decision
- cost floor state
- blocker or noop reason
- runner-up review
- shadow candidate evaluation

## Per-Trade Questions

Record `PASS`, `WATCH`, or `FAIL` for each completed trade.

| Question | Evidence Source | Status | Notes |
| --- | --- | --- | --- |
| Why was the top candidate accepted or rejected? | scanner output, entry quant decision, blocker/noop reason |  |  |
| Why was a runner-up selected? | runner-up review, scanner ranking, commander selection reason |  |  |
| Did `cost_floor_state` correctly block weak opportunities? | cost floor state, entry quant decision, trade result or shadow result |  |  |
| Did `tactic_suitability` match actual trade quality? | quant tactic output, trade report, PnL, post-exit shadow |  |  |
| Were volume and pullback quality signals correct? | pullback quality gate, volume diagnostics, minute candles |  |  |
| Were shadow candidates actually inferior? | shadow candidate evaluation, forward outcomes |  |  |
| Did `intraday_low_break` trigger too aggressively? | exit quant decision, monitor exit reason, post-exit shadow |  |  |
| Were exits occurring after significant profit fade? | max favorable excursion, exit price, post-exit shadow |  |  |

## Daily Checklist

| Gate | Required Result | Status | Notes |
| --- | --- | --- | --- |
| Artifact presence | all required artifacts exist for each executed trade |  |  |
| Broker/lifecycle/report alignment | broker truth, lifecycle truth, and report truth agree |  |  |
| Trade count alignment | broker order/fill count and report count are explainable |  |  |
| PnL alignment | realized PnL and PnL percent use the same truth source |  |  |
| Tactic field coverage | tactic id, suitability, cost floor, blockers are populated |  |  |
| Shadow coverage | candidates and forward outcomes are available or have an explicit missing reason |  |  |
| Post-exit coverage | +5/+15/+30/+60 minute checkpoints are filled or have an explicit missing reason |  |  |
| No behavior drift | validation work did not change runtime behavior |  |  |

## Critical Defect Definition

Only these findings justify interrupting validation and patching immediately:

- broker truth mismatch that changes trade status, quantity, price, or PnL
- executed trade without a lifecycle/report artifact
- report count materially diverges from broker order/fill count without a
  documented reason
- closed trade missing entry or exit quant decision
- execution behavior contradicts documented guard or commander authority
- artifact corruption that prevents reconstructing a trade

All other findings should be recorded as validation evidence first.

## Daily Output

At the end of each live validation day, produce a short validation note:

- validation date
- number of broker-confirmed trades
- number of trade reports
- artifact integrity status
- Q8 evidence status
- critical defects
- watch items
- behavior-change recommendation: `none`, `defer`, or `requires separate review`
