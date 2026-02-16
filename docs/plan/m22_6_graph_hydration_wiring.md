# M22-6: Graph Spine Wiring for Skill Hydration

- Date: 2026-02-16
- Goal: wire skill hydration into the canonical graph spine so Scanner/Monitor receive hydrated skill inputs during normal graph runs.

## Scope (minimal)

1. Add hydration hook to `run_trading_graph`.
2. Execute hydration before scanner on initial pass and retry loops.
3. Keep hydration disabled by default unless enabled by state (`use_skill_hydration`) or `skill_runner` presence.
4. Add graph-level wiring tests and runnable demo.

## Implemented

- File: `graphs/trading_graph.py`
  - Added optional `hydrate` node injection parameter.
  - Wired hydration call before scanner in initial pass and retry loop.
  - Activation policy:
    - enabled when `state["use_skill_hydration"]` is truthy, or
    - enabled when `state["skill_runner"]` exists.

- File: `tests/test_m22_graph_hydration_wiring.py`
  - Added tests for:
    - default no-hydration behavior
    - flag-enabled hydration with retry path
    - `skill_runner`-triggered auto hydration
    - graph hydration demo outputs (normal + timeout mode)

- File: `scripts/demo_m22_graph_with_hydration.py`
  - Added one-shot graph demo using `run_trading_graph(...)` with fake runner.
  - Supports `--simulate-timeout` fallback visibility.

## Safety Notes

- Existing graph behavior is preserved when hydration is not enabled.
- Hydration failures remain observable through `skill_fetch` and scanner/monitor fallback fields.
