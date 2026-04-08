# Commander LLM Execution Profile Migration Phase 4

## Purpose
Move LLM execution tuning ownership from env to Commander-applied policy.

This phase keeps trading semantics unchanged. It only changes where execution
profile values come from.

## Ownership
- Commander owns LLM execution profile choice
- Strategist and Reporter consume execution profile policy
- env keeps provider, endpoint, base URL, secrets, and hard guards
- `applied_policy.llm.*` is the single source of truth

## Removed env keys
- `REPORTER_AI_REVIEW_TEMPERATURE`
- `REPORTER_AI_REVIEW_MAX_TOKENS`
- `AI_STRATEGIST_TIMEOUT_SEC`
- `AI_STRATEGIST_MAX_TOKENS`
- `AI_STRATEGIST_RETRY_MAX`

## Canonical policy paths
- `applied_policy.llm.strategist.execution_profile.name`
- `applied_policy.llm.strategist.execution_profile.temperature`
- `applied_policy.llm.strategist.execution_profile.max_tokens`
- `applied_policy.llm.strategist.execution_profile.timeout_sec`
- `applied_policy.llm.strategist.execution_profile.retry_max`

- `applied_policy.llm.reporter.intraday.execution_profile.name`
- `applied_policy.llm.reporter.intraday.execution_profile.temperature`
- `applied_policy.llm.reporter.intraday.execution_profile.max_tokens`

- `applied_policy.llm.reporter.daily.execution_profile.name`
- `applied_policy.llm.reporter.daily.execution_profile.temperature`
- `applied_policy.llm.reporter.daily.execution_profile.max_tokens`

## Baseline execution profiles
- strategist: `balanced_reasoning`
  - `temperature = 0.1`
  - `max_tokens = 8192`
  - `timeout_sec = 15`
  - `retry_max = 2`
- reporter intraday: `concise_review`
  - `temperature = 0.2`
  - `max_tokens = 8192`
- reporter daily: `deep_review`
  - `temperature = 0.2`
  - `max_tokens = 8192`

## Model selection vs execution profile
- model selection answers: which model card/profile should run
- execution profile answers: how that model call should run
- Commander now owns both:
  - model profile under `applied_policy.llm.*.profile`
  - execution profile under `applied_policy.llm.*.execution_profile`

## Consumer policy
- Strategist reads Commander-applied execution profile and does not own timeout,
  token budget, or retry count
- Reporter surfaces read Commander-applied execution profile and do not own
  review temperature or token budget
- explicit function argument overrides remain available for narrow compatibility
  cases

## Runtime semantics
- trading semantics unchanged
- threshold / guard / execution behavior unchanged
- report output path and report meaning unchanged

## Remaining env-owned LLM values
- provider API keys / secrets
- provider endpoints / base URLs
- provider-specific infra metadata
- generic compatibility fallbacks in non-canonical legacy callers
