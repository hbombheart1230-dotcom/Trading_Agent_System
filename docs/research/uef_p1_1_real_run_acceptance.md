# UEF P1.1 Real-Run Acceptance

Status: **PASS**

P1.1 is a post-freeze operational verification of the already-frozen Unified Evaluation Framework. It
does not alter, reopen, or create UEF semantic authority. Formal freeze remains the semantic and contract
approval; this record is evidence that the frozen chain operated correctly on a current real input.

## Acceptance Record

- Acceptance code HEAD: `4f483262216a0bebcf8af6878bab05eb2a507466`
- Remote synchronization: pushed and verified at the same HEAD on `codex/observability-20260824`.
- Capture: `REAL_RUN_CAPTURE_A`, `through_day=2026-09-29`, `candidate_count=14`.

## Frozen Chain Result

| Stage | Run ID | Result |
|---|---|---|
| UEF-7 | `UEF7RUN_72da28ace5de04ef` | 14 candidates; 5 shared-source groups; 14 population statuses not provable from the current Alpha Board schema. |
| UEF-8 | `UEF8RUN_433a3c5d1677cf12` | 91 pairs; 0 COMPARABLE, 7 CONDITIONAL, 84 NOT_COMPARABLE; 91 unique pair IDs. |
| UEF-9 | `UEF9RUN_8cf4ef82b965db09` | `authority_status=VALID`; exact UEF-7 and UEF-8 bindings verified. |

The UEF-8 pair count satisfied `N*(N-1)/2`, and the current frozen-schema capability remained
`COMPARABLE_REACHABLE_WITH_CURRENT_UEF7_SCHEMA: NO`.

## Integrity Checks

- End-to-end UEF-8 to UEF-7 and UEF-9 to UEF-7/UEF-8 bindings: PASS.
- Same immutable Capture A replay: PASS; UEF-7, UEF-8, and UEF-9 IDs and semantic outputs were identical.
- Tamper checks: wrong UEF-7 binding, duplicate pair ID, status-count contradiction, and injected
  COMPARABLE capability contradiction were all rejected fail-closed.
- Production/runtime write isolation: PASS. Acceptance used in-memory objects and did not write data,
  broker, runtime, strategy, or execution state.
- Freeze manifest: `11 / 11 MATCH`.

## Current Follow-up

P1.2 cross-day observation is non-blocking: observe at least three trading days for continuing
`authority_status=VALID`, no authority mismatch or artifact corruption, and deterministic replay for an
identical captured input. Current execution priority is **P1.3 Docker**; Strategy Program Integration
remains P2.

## Related

- [UEF milestone](../milestones/UEF.md)
- [UEF-7 freeze](uef7_alpha_board_normalization_freeze.md)
- [UEF-8 freeze](uef8_fair_comparison_validation_freeze.md)
- [UEF-9 freeze](uef9_formal_evaluation_authority_freeze.md)
- [P1.1 daily patch note](../daily_patch/2026-09-29_uef_p1_1_real_run_acceptance.md)
