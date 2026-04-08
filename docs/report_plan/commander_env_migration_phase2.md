# Commander Env Migration Phase 2

## Summary
Phase 2 moves numeric runtime behavior parameters from env into Commander-owned
applied policy.

The goal is ownership migration, not runtime behavior change. Commander selects
the baseline values and injects them through `state["applied_policy"]`.
Downstream agents consume those values and do not own the final choice.

## Removed numeric env keys
- `POST_EXIT_COOLDOWN_SEC`
- `EXIT_POLICY_EOD_FLAT_CUTOFF_MIN`
- `MIN_HOLD_SECONDS`
- `SELL_COOLDOWN_SEC`
- `MONITOR_EXIT_CONFIRM_TICKS`
- `TOP_CANDIDATE_POOL`
- `KIWOOM_CANDIDATE_CONDITION_LIMIT`
- `MONITOR_ENTRY_SCORE_THRESHOLD`
- `STRATEGY_MEMORY_RECENT_RUNS`

## Canonical applied policy paths
- `applied_policy.execution.cooldowns.post_exit_sec`
- `applied_policy.execution.cooldowns.sell_sec`
- `applied_policy.monitor.hold.min_hold_seconds`
- `applied_policy.monitor.exit.confirm_ticks`
- `applied_policy.monitor.exit.eod_flat.cutoff_min`
- `applied_policy.scanner.candidate.top_pool`
- `applied_policy.scanner.kiwoom.condition_limit`
- `applied_policy.monitor.entry.scoring.threshold`
- `applied_policy.strategist.memory_feedback.recent_runs`

## Phase 2 baseline values
- `execution.cooldowns.post_exit_sec = 180`
- `execution.cooldowns.sell_sec = 300`
- `monitor.hold.min_hold_seconds = 600`
- `monitor.exit.confirm_ticks = 2`
- `monitor.exit.eod_flat.cutoff_min = 10`
- `scanner.candidate.top_pool = 30`
- `scanner.kiwoom.condition_limit = 200`
- `monitor.entry.scoring.threshold = 3`
- `strategist.memory_feedback.recent_runs = 12`

## Ownership and trace
- Commander is the owner of numeric runtime behavior choices.
- `applied_policy` is the canonical source of truth.
- Consumers may keep state/policy fallback paths during transition, but env is
  no longer the authority for these values.
- Operator-visible traces should show Commander ownership through:
  - `commander_applied_policy_summary.numeric_fields`
  - `policy_sources.commander_owned_numeric_fields`
  - role-specific `*_policy_source` metadata

## Runtime semantics unchanged
This migration does not change:
- Monitor order prohibition
- Supervisor / Executor / Guard precedence
- execution approval behavior
- risk guard semantics
- route taxonomy semantics

The migration only changes where numeric runtime behavior parameters are owned
and injected.

## What remains in env
Phase 2 still leaves these categories in env:
- secrets and credentials
- provider and endpoint settings
- hard safety guards
- model names, retry, timeout, and token budgets
- log and report paths
- scanner fallback strictness and broader source-selection policy
- optional hard caps such as `TOP_N_CANDIDATES`
