# Q9 Horizon Contract Observability

Date: 2026-06-26

## Purpose

Q9 now evaluates whether actual exits respected the Strategist/Commander
intended holding window.

This is observability only. It does not change:

- entry logic
- exit logic
- scanner ranking
- strategist prompts
- commander approval
- order execution

## Problem Fixed

Previous Q9 evaluation compared Scanner, Strategist, Commander, Monitor, and
forward returns, but it did not make the intended holding period a first-class
evaluation axis.

That made it hard to distinguish:

- bad symbol selection
- late entry
- premature exit
- valid hard-stop exit
- strategy horizon mismatch

## Horizon Contract

Each Q9 trade read model now attempts to extract:

- `strategy_horizon`
- `source_strategy_horizon`
- `expected_hold_window.min_sec`
- `expected_hold_window.target_sec`
- `expected_hold_window.max_sec`
- `early_exit_allowed_reasons`
- `avoid_early_exit_reasons`
- `profit_take_style`
- `hold_control_bias`
- `observability_only`
- `allow_behavior_change`
- `do_not_force_hold`

The source is the existing runtime horizon policy artifacts, including
Commander horizon policy and Strategist horizon proposal.

## Evaluation Output

Each trade evaluation now includes:

```text
horizon_alignment
```

Key fields:

- `bucket`
  - `before_min_hold`
  - `before_target_hold`
  - `within_target_window`
  - `beyond_max_hold`
- `exited_before_min_hold`
- `exited_before_target_hold`
- `valid_early_exit`
- `horizon_violation_candidate`
- `target_hold_would_improve_exit`
- `early_exit_cost_pct`

Daily scorecards now aggregate:

- observed horizon contracts
- exits before minimum hold
- exits before target hold
- horizon violation candidates
- cases where target hold would have improved the exit
- average early-exit cost

## Interpretation

A trade can exit before the intended hold window without being a violation if
the exit reason matches a hard invalidator such as stop loss, liquidity
collapse, broker truth mismatch, market regime flip, or forced closeout.

A trade becomes a horizon violation candidate when:

- it exits before the intended minimum hold without a valid early-exit reason,
  or
- it exits before the target hold and post-exit evidence shows the target hold
  would likely have improved the exit.

## Q9 Window Handling

The five-valid-day Q9 window is not restarted.

This change is additive observability. It improves attribution quality during
the current evaluation window and may be applied to historical trades through
Q9 regeneration.

If evidence is insufficient after the fixed Q9 window, only the horizon
alignment sub-question may require a short supplemental review. The entire Q9
program must not be extended merely because horizon evidence is incomplete.
