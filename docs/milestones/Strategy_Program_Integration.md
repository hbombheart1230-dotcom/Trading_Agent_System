# Strategy Program Integration

## Status

Architecture classification decision. This note does not create a runtime milestone or imply a code change.

## Rule

Q9 through Q18 and `Opening` are legacy research and provenance labels, not an architecture category. A Q label is not, by default, an independent agent or a permanent execution lane.

Programs must be classified as a strategy program, experiment, baseline, policy, evaluation consumer, or report/view. The evidence classification is authoritative in [UEF-4A legacy family inventory](../research/uef4_legacy_family_inventory.md): 39 sources total, 20 primary-evidence sources, and 19 derived or consumer sources.

## Lifecycle Authority

The canonical runtime lifecycle remains:

`Commander -> Strategist -> Scanner -> Monitor -> Reporter -> Supervisor -> Executor`

No program classification creates an eighth role or bypasses the existing guard chain.

## Standing Rules

- **No new Q by default.** A hypothesis remains an experiment until evidence and role are explicitly classified.
- **No new lane by default.** Forward-return evidence does not independently create a live execution lane.
- **No silent promotion.** An experiment, utility, data source, or report never becomes a Q, agent, lane, or authority without an explicit decision.

The durable decision record is [[ADR-0002_Q_Namespace_Freeze_and_Seven_Node_Lifecycle_Authority|ADR-0002]].

## Related

- [[UEF]]
- [[ADR-0002_Q_Namespace_Freeze_and_Seven_Node_Lifecycle_Authority|ADR-0002]]
