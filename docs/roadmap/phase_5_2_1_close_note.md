# Phase 5-2-1 Close Note

## Summary
Phase `5-2-1: Pre-buy strategist refresh` is now in a good stopping state.
Within the narrowed scope we have implemented commander-owned strategist refresh / reuse orchestration with additive provenance and targeted regression coverage.

This note does not replace the roadmap.
It only records what is considered complete enough for the current `5-2-1` slice.

## What Was Completed
The current implementation now covers these behaviors:
- commander decides whether the next cycle should reuse cached strategist context or rebuild a fresh strategist frame
- strategist refresh is no longer owned by environment toggles
- cached strategist reuse no longer owns refresh policy; it follows commander intent
- strategist refresh provenance is preserved through commander decision, strategist output, and commander artifact
- runtime shadow still records whether refresh was actually taken

## Refresh Triggers Currently Covered
Commander can now request fresh strategist context when any of these conditions indicate the cached frame is no longer the right planning frame:
- near-entry transition became ready this cycle
- transition readiness score crossed the local threshold
- selected symbol is outside the cached strategist frame
- market regime shifted since cache generation
- news query targets drifted from the cached strategist frame

## Cache Reuse Conditions Currently Covered
Commander can prefer cached strategist reuse when:
- state is flat
- cached strategist output exists
- cache age stays within reuse window
- no forced refresh is present
- no commander-requested refresh condition is active

## Ownership Boundary
The current boundary is intentional and should stay narrow:
- Commander: decide refresh vs reuse at the orchestration layer
- Strategist: gather fresh context/news when refresh is requested
- Scanner / Monitor: consume the resulting frame deterministically

This is still not a full policy ownership step.
It remains below Phase 5-3 and should not be expanded into a global policy schema here.

## Why 5-2-1 Can Pause Here
The current slice already achieves the practical goal of `5-2-1`:
- stale cached strategist reuse is less blind
- refresh timing is owned by commander rather than env toggles
- provenance is visible enough to debug decisions after the fact

Further expansion here would start pushing into later-phase concerns such as:
- broader strategist policy ownership
- scanner / monitor contract redesign
- policy object semantics

Those belong after this step, not inside it.

## Test Snapshot
Targeted regression coverage currently passes for the implemented slice:
- `tests/test_m21_commander_runtime_entry.py`
- `tests/test_phase1_agent_artifact_quality.py`

## Next Step
The next roadmap step should be `5-2-2: 가시화 (뉴스 -> 종목 연결)`.
That step is a better place to make the strategist refresh behavior legible in downstream inspection surfaces, without expanding `5-2-1` into a larger policy project.

## Practical Read
Treat `5-2-1` as functionally complete for now.
Use the current implementation as the refresh/reuse orchestration baseline, and move the next development focus to `5-2-2`.
