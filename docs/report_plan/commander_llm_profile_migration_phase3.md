# Commander LLM Profile Migration Phase 3

## Purpose
Move LLM model selection ownership from env to Commander-applied policy.

This phase keeps trading semantics unchanged. It only changes where model
selection comes from.

## Ownership
- Commander owns model selection
- downstream agents consume model policy
- env keeps provider, endpoint, timeout, retry, and token budget
- `applied_policy.llm` is the single source of truth

## Canonical policy paths
- `applied_policy.llm.strategist.profile`
- `applied_policy.llm.strategist.primary`
- `applied_policy.llm.strategist.fallback`
- `applied_policy.llm.reporter.intraday.profile`
- `applied_policy.llm.reporter.intraday.primary`
- `applied_policy.llm.reporter.intraday.fallback`
- `applied_policy.llm.reporter.daily.profile`
- `applied_policy.llm.reporter.daily.primary`
- `applied_policy.llm.reporter.daily.fallback`

## Baseline profiles
- strategist: `balanced`
- reporter intraday: `fast_free`
- reporter daily: `strong_reasoning`

## Catalog baseline
- `minimax/minimax-m2.5`
- `deepseek/deepseek-v3.2`
- `moonshotai/kimi-k2.5`

## Consumer policy
- Strategist reads Commander-applied LLM policy and does not select models itself
- Reporter surfaces read Commander-applied LLM policy and do not select models itself
- explicit function argument overrides remain available for narrow compatibility cases

## Runtime semantics
- trading semantics unchanged
- threshold / guard / execution behavior unchanged
- report output path and report meaning unchanged
