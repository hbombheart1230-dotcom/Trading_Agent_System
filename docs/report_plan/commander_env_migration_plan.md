# Commander-Centric Configuration Migration Plan

## Goal
Move runtime behavior toggles out of env and into Commander-owned applied policy.

## Principles
- Commander owns configuration choice and policy authority.
- `state["applied_policy"]` is the preferred source of truth.
- Env should shrink toward infra, secrets, providers, hard guards, and numeric operating parameters.
- Strategist, Reporter, Scanner, and Monitor consume configuration; they do not own runtime behavior toggles.

## Phase 1 scope
Phase 1 migrates behavior toggles with mode, strict, legacy, route, memory, and scoring semantics.

### Reporter
- `REPORTER_AI_REVIEW_ENABLED` -> `applied_policy.reporter.ai_review.enabled`
- `TRADE_REPORT_AI_ENABLED` -> `applied_policy.reporter.trade_report.enabled`
- `TRADE_REPORT_AI_GENERATE_ON_OPEN` -> `applied_policy.reporter.trade_report.generate_on_open`

### Strategist runtime and legacy gating
- `AI_STRATEGIST_STRICT` -> `applied_policy.strategist.runtime.strict_mode`
- `ALLOW_LEGACY_RULE_RUNTIME` -> `applied_policy.strategist.runtime.allow_legacy_rule`
- `ALLOW_LEGACY_STRATEGY_V1_RUNTIME` -> `applied_policy.strategist.runtime.allow_legacy_strategy_v1`
- `USE_STRATEGY_MEMORY_FEEDBACK` -> `applied_policy.strategist.memory_feedback.enabled`

### Commander route policy
- `COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED` -> `applied_policy.commander.route.monitor_only_when_holding`
- `COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED` -> `applied_policy.commander.route.cached_strategist_when_flat`

### Monitor scoring toggles
- `MONITOR_SCORING_ENABLED` -> `applied_policy.monitor.entry.scoring.enabled`
- `MONITOR_SCORING_SHADOW_MODE` -> `applied_policy.monitor.entry.scoring.shadow_mode`

## What remains in env
Env remains appropriate for:
- API keys and secrets
- provider selection, endpoints, model names, timeouts, retries, token limits
- hard safety guards and real-execution gating
- numeric operating parameters that have not yet been migrated
- report and log paths

## Runtime semantics
This migration is ownership-only.

It must not change:
- Monitor order prohibition
- Supervisor / Executor / Guard precedence
- execution approval or risk semantics
- trade thresholds or route taxonomy semantics

## Observability
Commander should expose enough metadata to show that behavior toggles came from commander-applied policy rather than env. Recommended metadata includes:
- `commander_applied_policy_summary`
- `policy_sources.commander_owned_fields`
- consumer-specific `policy_source` fields where already supported
