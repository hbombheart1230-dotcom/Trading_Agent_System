# M21-3: Decision Packet Activation Guard

- Date: 2026-02-15
- Goal: prevent accidental switch to `decision_packet` runtime mode from state/env settings.

## Scope (minimal)

1. Add activation guard for non-explicit `decision_packet` mode selection.
2. Keep explicit mode argument as deliberate override for callers/tests.

## Implemented

- File: `graphs/commander_runtime.py`
  - Added guard policy:
    - `decision_packet` via `state["runtime_mode"]` or env `COMMANDER_RUNTIME_MODE`
      requires one of:
      - `state["allow_decision_packet_runtime"]=true`
      - env `COMMANDER_RUNTIME_ALLOW_DECISION_PACKET=true`
  - Explicit `mode="decision_packet"` still works as caller-controlled override.

- File: `tests/test_m21_commander_runtime_entry.py`
  - Updated mode routing tests to include activation conditions.
  - Added guard-block test when activation is missing.

## Safety Notes

- Default runtime remains `graph_spine`.
- No execution guard/risk policy behavior changed.
