# Env Rules

## Principle
Commander owns configuration choice and policy authority.

We minimize env-driven toggles over time. If a setting is needed, it should be
selected by Commander and injected through commander-applied policy or runtime
state, rather than owned independently by downstream agents.

## Rules
- do not add new env toggles when Commander can make the decision
- do not create agent-local ownership for runtime behavior flags
- prefer `state["applied_policy"]` or other Commander-owned runtime state
- Strategist, Reporter, Scanner, and Monitor are consumers, not owners

## Practical direction
- env should shrink over time
- Commander-applied policy is the preferred source of truth
- runtime state may be used as a transitional fallback
- downstream agents may read configuration, but should not own final choice
