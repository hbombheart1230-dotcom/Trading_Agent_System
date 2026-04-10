# Phase 4 Close: LLM Execution Profile Migration

## Summary
LLM execution tuning ownership moved to Commander-applied policy.

## Key Changes
- `applied_policy.llm.execution_profile` added as the canonical execution profile baseline
- execution profile schema normalized:
  - `profile_name`
  - `temperature`
  - `max_tokens`
  - `timeout_sec`
  - `retry.max_attempts`
  - `retry.backoff_sec`
- Strategist and Reporter LLM call paths now prefer Commander-applied execution profile values
- env fallback remains available for compatibility only when execution profile is missing
- LLM artifacts now expose:
  - `llm_execution_profile_name`
  - `llm_execution_profile_source`
  - `llm_execution_effective_config`

## Result
Commander now owns LLM execution tuning posture while runtime behavior stays unchanged.

## Validation
- LLM/profile tests passed
- strategist/reporter continuity tests passed
- no trading semantics change

## Remaining
- role-scoped execution profile compatibility slots still exist
- broader legacy LLM caller cleanup can continue in later phases

## Status
CLOSED
