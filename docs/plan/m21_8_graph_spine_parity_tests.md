# M21-8: Graph Spine Parity Tests

- Date: 2026-02-15
- Goal: prove canonical commander runtime (`graph_spine` mode) preserves legacy graph behavior.

## Scope (minimal)

1. Add parity tests between `run_trading_graph` and `run_commander_runtime(..., mode="graph_spine")`.
2. Cover approve path and retry-scan path.
3. Avoid runtime behavior changes (tests + docs only).

## Implemented

- File: `tests/test_m21_graph_spine_parity.py`
  - Added approve-path parity test.
  - Added retry-scan parity test (`retry_scan -> approve` loop).
  - Uses injected noop logger to keep tests offline and deterministic.

## Safety Notes

- No production code behavior changed in this milestone.
- Parity tests provide regression guard during future M21 consolidation work.
