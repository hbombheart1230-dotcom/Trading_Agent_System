# Existing Evidence Mining Contract

## Purpose

Use all trustworthy evidence already collected before requesting another live
observation window.

The study reconstructs:

`Q9 candidate appearance -> source and rank -> next tradable minute -> forward path`

It separately reviews:

- Q16 blocked candidates with observed forward paths
- actual trade evaluations and horizon compliance
- candidate-universe source contamination
- score-component diagnostic separation
- fixed target/stop path policies

## Boundary

- offline only
- no LLM
- no graph
- no order intent
- no runtime behavior change
- no Scanner, Strategist, Commander, Monitor, entry, or exit modification
- July is inspected retrospective data, not an untouched holdout

## Evidence Classes

Scanner episodes:

`RECONSTRUCTED_FROM_POINT_IN_TIME_Q9`

Blocked opportunities:

Q16 samples are retained as a separate dataset and are not merged as
independent Scanner trades.

Repeated Q16 decision IDs that reference the same symbol and baseline minute
are one opportunity. The richest observed row is retained.

The primary blocker reconstruction uses all available
`data/logs/quant_shadow_candidates` days. It reads the earliest point-in-time
snapshot in each fixed 15-minute clock bucket, deduplicates symbol/minute
records, and then keeps at most one episode per symbol every 15 minutes.
Forward paths are reconstructed from the historical minute cache. Q16 remains
a reference inventory rather than the primary sample.

Actual trades:

The existing `trade_evaluation.v1` integrity and promotion eligibility fields
remain authoritative.

## Fixed Assumptions

- live round-trip cost: 0.28%
- horizons: +5m, +15m, +30m, +60m, EOD
- primary diagnostic horizon: +30m
- repeated Q9 windows: one episode per symbol every 15 minutes
- candidate ranks: Top 10 when available
- entry price: first one-minute candle open strictly after the decision
- same-bar target and stop collision: stop first

## Required Outputs

- candidate-universe integrity
- rank-bucket performance
- source and source-confluence performance
- time-bucket performance
- score-component high/low diagnostic delta
- Monitor/Q16 blocker opportunity cost
- fixed target/stop path comparison
- actual trade horizon diagnostics
- one bounded research decision

Discovery cohorts may be reported only as retrospective findings. Any cohort
created after inspecting the result must be labeled
`FUTURE_CONFIRMATION_REQUIRED` and cannot authorize a runtime patch.

## Decision Rule

This study cannot directly promote policy.

A positive result may create at most one future-confirmation candidate. A
negative result closes the candidate without another automatic observation
extension.

## Integrity Correction

The first implementation used the open of the already-started decision candle.
That was not tradable after the decision timestamp. On 2026-07-31 the shared
offline entry helper was corrected to use the first candle timestamp strictly
after the decision, and the complete result was regenerated through the fixed
2026-07-30 close. The implementation day is not part of the retrospective
sample.
