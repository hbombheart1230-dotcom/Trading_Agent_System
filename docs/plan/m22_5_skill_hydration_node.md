# M22-5: Skill Hydration Node for Scanner/Monitor Pipeline

- Date: 2026-02-15
- Goal: add a dedicated node that fetches composite-skill outputs and hydrates `state["skill_results"]` before Scanner/Monitor consumption.

## Scope (minimal)

1. Add node-level skill fetch orchestration (`market.quote`, `account.orders`, `order.status`).
2. Keep Scanner/Monitor logic unchanged (consume already-hydrated state).
3. Add fetch telemetry summary in state for operators/tests.
4. Add offline demo path with fake runner.

## Implemented

- File: `graphs/nodes/hydrate_skill_results_node.py`
  - Added `hydrate_skill_results_node(state)`:
    - reads `state["skill_runner"]`
    - fetches:
      - `market.quote` for candidate symbols
      - `account.orders` once
      - `order.status` when `state["order_ref"]` is provided
    - writes canonical `state["skill_results"]`
    - writes fetch summary `state["skill_fetch"]`:
      - `attempted`, `ready`, `errors_total`, `errors`

- File: `scripts/demo_m22_skill_hydration.py`
  - Added runnable demo for hydration + scanner + monitor flow.
  - Added `--simulate-timeout` mode for fallback visibility.

- File: `tests/test_m22_skill_hydration_node.py`
  - Added happy-path hydration test.
  - Added failure-path safe fallback test.
  - Added demo script output contract tests.

## Safety Notes

- If `skill_runner` is missing, node is no-op with explicit `skill_fetch.used_runner=false`.
- No approval/execution path behavior changed.
