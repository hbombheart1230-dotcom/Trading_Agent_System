# ADR-0002: Q Namespace Freeze and Seven-Node Lifecycle Authority

## Status

Accepted.

## Decision

`Q` labels are legacy research and provenance labels, not architecture.

- A new experiment does not create a new Q by default.
- A new utility does not create a new agent.
- A new data source does not create a new execution lane.
- A new report does not create a new authority.
- Promotion is never silent; evidence and lifecycle ownership must be explicit.

Strategy programs, experiments, policies, and reports ultimately remain owned by one or more existing lifecycle roles:

`Commander -> Strategist -> Scanner -> Monitor -> Reporter -> Supervisor -> Executor`

## Consequences

Q labels may organize provenance and evaluation, but cannot bypass role boundaries or grant execution authority. Classification and current examples are maintained in [[Strategy_Program_Integration|Strategy Program Integration]].

## Authority

- [Agent role rules](../ground_rules/AGENT_RULES.md)
- [[Strategy_Program_Integration|Strategy Program Integration]]
- [UEF-4A legacy family inventory](../research/uef4_legacy_family_inventory.md)
