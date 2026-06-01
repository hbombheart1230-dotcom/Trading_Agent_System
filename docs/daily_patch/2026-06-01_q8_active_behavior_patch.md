# 2026-06-01 Q8 Active Behavior Patch

## Problem

Q8 had enough evidence for some decisions but kept presenting the work as
"sample insufficient" because all evidence types were treated the same.

Actual closed trades are required for realized PnL and exit/hold conclusions,
but deterministic pre-entry guards can be promoted from shadow candidates
because their inputs are known before an order is sent.

## Decisions

1. Keep Q8, but stop using it as a passive waiting phase.
2. Split promotion into three evidence classes:
   - deterministic pre-entry guard
   - strategy/lane allocation
   - exit/hold behavior
3. Promote `vwap_reclaim_pullback` quality gate.
4. Add shadow forward baseline/outcome reporting so shadow can become a real
   strategy evaluation surface, not only a blocker count surface.

## Live Behavior Patch

`vwap_reclaim_pullback` is blocked when suitability is not strong and the setup
is not mature.

Required mature setup:

- cost OK
- volume OK
- VWAP reclaim OK
- pullback OK or breakout OK
- confidence above threshold buffer

If not satisfied, monitor emits:

- `vwap_pullback_promoted_quality_gate`

The entry enforcement layer treats this blocker as a hard guard.

## Reporting Patch

Shadow candidates now expose:

- top-level tactic ID from nested `entry_quant_decision` or factor snapshot
- tactic suitability tier/score from nested decision payload
- cost floor state from decision/factor snapshot
- baseline minute price when runtime minute rows are available
- forward checkpoint outcome coverage in operator summaries

## Why This Is Not Just More Observation

The behavior patch changes live entry permission. The shadow changes are for
the next promotion targets: runner-up cascade, opening momentum, breakout
allocation, and long-horizon/hold decisions.
