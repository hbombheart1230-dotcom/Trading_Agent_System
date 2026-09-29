# Trading Agent System

## Current State

- Production runtime: separate from this documentation vault.
- Current development milestone: UEF-9 Formal Evaluation Authority Freeze (NEXT).
- Latest formal evaluation freeze: [[UEF|UEF-8 - Fair Comparison Validation]].

## Roadmap Sequence

Forward-looking ordering of the major workstreams (status as currently tracked; later items remain
PLANNED and are not yet architected in detail):

1. UEF-5.1 Clean Evidence Registry — FORMALLY FROZEN
2. UEF-5.2 Historical Recompute — FORMALLY FROZEN
3. UEF-5.3 Historical Dual Run — FORMALLY FROZEN
4. UEF-6 Dedup & Evidence Lineage — FORMALLY FROZEN
5. UEF-7 Alpha Board Normalization — FORMALLY FROZEN
6. UEF-8 Fair Comparison Validation — FORMALLY FROZEN
7. UEF-9 Evaluation Authority Freeze — NEXT
8. UEF COMPLETE (target)
9. [[Strategy_Program_Integration|Strategy Program Integration]] — architecture classification decision, ongoing
10. Safety Step5D / Step5E / Step6 — PLANNED (Step5C is FROZEN; see [[Safety]])
11. [[Reporter_Q100|Q100 / Reporter v2]] — DESIGN STAGE
12. [[Evidence_Memory|Evidence Memory + Obsidian]] — PLANNED
13. Self-Improvement Loop — PLANNED (see [[System_V2|System V2]] dependencies)
14. [[System_V2|System V2 Formal Freeze]] — PLANNED
15. Paper Final Experiments — PLANNED
16. Paper Writing — PLANNED

## Major Workstreams

- [[UEF]]
- [[Strategy_Program_Integration|Strategy Program Integration]]
- [[Safety]]
- [[Reporter_Q100|Reporter Q100]]
- [[Evidence_Memory|Evidence Memory]]
- [[System_V2|System V2]]

## Core Architecture

- [Architecture overview](architecture/architecture.md)
- [Architecture V2](architecture/architecture_v2.md)
- [Agent role authority](ground_rules/AGENT_RULES.md)
- [Unified Evaluation Foundation](research/unified_evaluation_foundation.md)

## Current UEF

- UEF-1 through UEF-3C: FORMALLY FROZEN.
- UEF-4A: FORMALLY FROZEN.
- UEF-4B (Q9-Q12, Opening, Q10 Semi/Index adapters): PROVISIONALLY COMPLETE.
- UEF-5.1, Clean Evidence Registry: FORMALLY FROZEN.
- UEF-5.2, Historical Recompute: FORMALLY FROZEN (one non-blocking debt item, `UEF5_2_DEBT_001`).
- UEF-5.3, Historical Dual Run: FORMALLY FROZEN (one non-blocking debt item, `UEF5_3_DEBT_001`).
- UEF-6, Dedup & Evidence Lineage: FORMALLY FROZEN. See [UEF-6 freeze record](research/uef6_dedup_evidence_lineage_freeze.md).
- UEF-7, Alpha Board Normalization: FORMALLY FROZEN. See [UEF-7 freeze record](research/uef7_alpha_board_normalization_freeze.md).
- UEF-8, Fair Comparison Validation: FORMALLY FROZEN. See [UEF-8 freeze record](research/uef8_fair_comparison_validation_freeze.md).
- UEF-9, Formal Evaluation Authority Freeze: NEXT.
- UEF-4A inventory detail: [Legacy family inventory](research/uef4_legacy_family_inventory.md).
- Full UEF status: [[UEF]].

## Operations

- [[2026-09-15_Live_Run_AMBER|2026-09-15 Live Run AMBER]]

## Architecture Decisions

- [[ADR-0002_Q_Namespace_Freeze_and_Seven_Node_Lifecycle_Authority|ADR-0002: Q Namespace Freeze and Seven-Node Lifecycle Authority]]
- [[ADR-0003_UEF5_2_Market_Data_Authority_and_Recompute_Identity|ADR-0003: UEF-5.2 Market-Data Authority and Recompute Identity]]

## Documentation Indexes

- [Korean index](ko/00_index.md)
- [English index](en/00_index.md)
- [Evaluation index](evaluation/README.md)
- [Offline alpha research index](offline_alpha/README.md)

This page is navigation only. Runtime and canonical artifacts remain the source of truth.
