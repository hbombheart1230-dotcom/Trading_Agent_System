# 2026-09-09 Exit Threshold and Horizon Integrity

## Scope

- Preserve the complete structural stop provenance used by Monitor exits.
- Prevent a cached Stage 3 hold review from being applied as a fresh decision.
- Keep the active Commander horizon maximum aligned with both Monitor hold limits.

## Changes

- Stage 3 and Stage 4 horizon revisions are applied only when both the current
  run ID and Strategist LLM call kind match the corresponding review stage.
- Stage 3 lineage copies the exact review evaluated by Commander and reports
  response/application action or horizon mismatches.
- When horizon behavior is active, `expected_hold_window.max_sec` now controls
  both `max_hold_sec` and `time_stop_sec`.
- Monitor artifacts now retain the entry stop source, invalidation price, raw
  structural stop, and minimum structural stop floor.

## Behavior Boundary

No Scanner ranking, entry eligibility, stop percentage, take-profit percentage,
broker routing, or execution safety rule was changed. The patch removes stale
horizon reuse and makes the already-selected horizon and entry-risk contract
internally consistent and reconstructable.

## Verification

- 33 focused assertions passed.
- The pytest process returned non-zero only because the concurrent live runtime
  changed production artifacts detected by the session manifest guard.
- Python compilation and `git diff --check` passed.
- The live runtime restarted successfully and resumed heartbeat/canonical output.
