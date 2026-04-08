# Commander Env Migration Phase 1

## Summary
Phase 1 moves behavior toggles from env into Commander-owned applied policy.

The intent is not to change runtime trading behavior. The intent is to make Commander the single owner of behavior selection while downstream agents consume canonical policy.

## Removed env keys
- `REPORTER_AI_REVIEW_ENABLED`
- `TRADE_REPORT_AI_ENABLED`
- `TRADE_REPORT_AI_GENERATE_ON_OPEN`
- `AI_STRATEGIST_STRICT`
- `ALLOW_LEGACY_RULE_RUNTIME`
- `ALLOW_LEGACY_STRATEGY_V1_RUNTIME`
- `USE_STRATEGY_MEMORY_FEEDBACK`
- `COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED`
- `COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED`
- `MONITOR_SCORING_ENABLED`
- `MONITOR_SCORING_SHADOW_MODE`

## Canonical applied policy paths
- `applied_policy.reporter.ai_review.enabled`
- `applied_policy.reporter.trade_report.enabled`
- `applied_policy.reporter.trade_report.generate_on_open`
- `applied_policy.strategist.runtime.strict_mode`
- `applied_policy.strategist.runtime.allow_legacy_rule`
- `applied_policy.strategist.runtime.allow_legacy_strategy_v1`
- `applied_policy.strategist.memory_feedback.enabled`
- `applied_policy.commander.route.monitor_only_when_holding`
- `applied_policy.commander.route.cached_strategist_when_flat`
- `applied_policy.monitor.entry.scoring.enabled`
- `applied_policy.monitor.entry.scoring.shadow_mode`

## Ownership model
- Commander chooses the behavior baseline.
- Commander injects the chosen values through applied policy and runtime state.
- Strategist, Reporter, Scanner, and Monitor consume those values.
- Env is reserved for infra, secrets, provider setup, hard guards, and selected numeric operating parameters.

## Baseline values in phase 1
The phase 1 baseline preserves current operating posture as closely as possible.

- `reporter.ai_review.enabled = false`
- `reporter.trade_report.enabled = true`
- `reporter.trade_report.generate_on_open = true`
- `strategist.runtime.strict_mode = true`
- `strategist.runtime.allow_legacy_rule = false`
- `strategist.runtime.allow_legacy_strategy_v1 = false`
- `strategist.memory_feedback.enabled = true`
- `commander.route.monitor_only_when_holding = true`
- `commander.route.cached_strategist_when_flat = false`
- `monitor.entry.scoring.enabled = false`
- `monitor.entry.scoring.shadow_mode = true`

## Runtime semantics unchanged
This migration does not change:
- Monitor order prohibition
- Supervisor / Executor / Guard precedence
- execution approval behavior
- route taxonomy semantics
- thresholds or risk limits

Reporter feedback and strategy memory remain advisory-only where they already were.

## Remaining env categories
Phase 1 intentionally leaves these in env:
- secrets and credentials
- provider and endpoint selection
- hard guards and real-execution safety controls
- model names, retry, timeout, and token budgets
- report and log paths
- selected numeric operating parameters such as cooldowns and windows

## Notes for operators
If a behavior toggle appears to be missing from `.env.example`, check Commander-applied policy first. That is now the canonical place to understand why the runtime behaved a certain way.
