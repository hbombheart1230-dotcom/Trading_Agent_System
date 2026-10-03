"""UEF-8 -- Fair Comparison Validation.

Given the frozen UEF-7 normalized Alpha Board, determines whether each
unordered pair of candidate rows is COMPARABLE, CONDITIONAL, or
NOT_COMPARABLE. Read-only against UEF-7 (schema
``uef7.alpha_board_normalization.v1``): never reopens raw Alpha Board
sources, never recalculates UEF-7's own source groups / source bundle ids
/ population statuses / normalized metrics, never modifies UEF-6 or UEF-7.

UEF-8 does NOT determine which candidate is better. It introduces no
score, rank, tier, winner, promotion recommendation, or strategy
recommendation of any kind -- comparison VALIDITY evidence only.
``comparable != better``, ``NOT_COMPARABLE != bad strategy``,
``CONDITIONAL != weak strategy``.
"""
