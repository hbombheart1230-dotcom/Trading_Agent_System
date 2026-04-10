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
- `applied_policy.llm.execution_profile.profile_name`
- `applied_policy.llm.execution_profile.temperature`
- `applied_policy.llm.execution_profile.max_tokens`
- `applied_policy.llm.execution_profile.timeout_sec`
- `applied_policy.llm.execution_profile.retry.max_attempts`
- `applied_policy.llm.execution_profile.retry.backoff_sec`

Compatibility role-scoped surfaces may still exist:
- `applied_policy.llm.strategist.execution_profile.*`
- `applied_policy.llm.reporter.intraday.execution_profile.*`
- `applied_policy.llm.reporter.daily.execution_profile.*`

Runtime callers prefer the canonical top-level execution profile first, then
role-scoped compatibility overrides, then env/default fallback when needed.

## Baseline execution profiles
- canonical baseline: `default_intraday`
  - `temperature = 0.2`
  - `max_tokens = 8192`
  - `timeout_sec = 15`
  - `retry.max_attempts = 2`
  - `retry.backoff_sec = 0.0`
- role-scoped execution profiles remain available as compatibility surfaces:
  - strategist: `balanced_reasoning`
  - reporter intraday: `concise_review`
  - reporter daily: `deep_review`

## Model selection vs execution profile
- model selection answers: which model card/profile should run
- execution profile answers: how that model call should run
- Commander now owns both:
  - model profile under `applied_policy.llm.*.profile`
  - canonical execution profile under `applied_policy.llm.execution_profile`
  - optional compatibility overrides under `applied_policy.llm.*.execution_profile`

## Consumer policy
- Strategist reads Commander-applied execution profile and does not own timeout,
  token budget, or retry count
- Reporter surfaces read Commander-applied execution profile and do not own
  review temperature or token budget
- Artifacts expose:
  - `llm_execution_profile_name`
  - `llm_execution_profile_source`
  - `llm_execution_effective_config`
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
