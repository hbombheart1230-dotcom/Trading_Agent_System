# M22-8: Auto CompositeSkillRunner Connection in Hydration Node

- Date: 2026-02-16
- Goal: allow hydration node to connect to a real `CompositeSkillRunner` path without mandatory manual runner injection.

## Scope (minimal)

1. Keep existing `state["skill_runner"]` path unchanged.
2. Add fallback runner resolution order:
   - `state["skill_runner"]`
   - `state["skill_runner_factory"]`
   - auto-build `CompositeSkillRunner.from_env()` (opt-in)
3. Keep failure-safe behavior with explicit error metadata.

## Implemented

- File: `graphs/nodes/hydrate_skill_results_node.py`
  - Added runner resolver with precedence:
    1) `state.skill_runner`
    2) `state.skill_runner_factory`
    3) auto runner when enabled:
       - `state["auto_skill_runner"]=true`, or
       - env `M22_AUTO_SKILL_RUNNER=true`
  - Added `skill_fetch.runner_source`:
    - `state.skill_runner`
    - `state.skill_runner_factory`
    - `auto.composite_skill_runner`
    - `none`
  - On auto/factory build failure, node remains safe and records errors.

- File: `tests/test_m22_skill_hydration_node.py`
  - Added tests for:
    - factory-based runner resolution
    - auto composite runner build path
    - auto runner build failure safety path
  - Existing tests updated to assert `runner_source`.

## Safety Notes

- Auto connection is opt-in only.
- No execution/approval guard behavior changed.
