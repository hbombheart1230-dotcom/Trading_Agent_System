# Operations Command Center

## Change

Added a modular, read-only command center with an operating timeline, anomaly
summary, trade decision lineage and bounded comparisons.

## Behavior Boundary

This patch changes observability only. Strategist, Scanner, Monitor, Commander,
Executor, evaluation, scheduling and Trading Runtime behavior are unchanged.

## Evidence Sources

- scheduled job manifests
- operational anomaly read model
- runtime status read model
- normalized trade detail and post-exit checkpoints

No missing value is converted into a favorable or unfavorable judgment.
