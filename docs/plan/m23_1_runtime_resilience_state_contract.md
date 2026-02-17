# M23-1: Runtime Resilience State Contract

- Date: 2026-02-17
- Goal: add one canonical runtime-level state contract for resilience and circuit status.

## Scope (minimal)

1. Define canonical state keys for resilience:
   - `state["resilience"]`
   - `state["circuit"]["strategist"]`
2. Ensure commander runtime always normalizes and injects these keys.
3. Add regression tests for default injection and legacy compatibility mapping.

## Implemented

- File: `libs/runtime/resilience_state.py`
  - Added `RUNTIME_RESILIENCE_CONTRACT_VERSION = "m23.resilience.v1"`.
  - Added `ensure_runtime_resilience_state(state)`:
    - injects default resilience/circuit keys when missing
    - normalizes types (`bool/int/enum`)
    - maps legacy top-level fields:
      - `circuit_state`
      - `circuit_fail_count`
      - `circuit_open_until_epoch`

- File: `graphs/commander_runtime.py`
  - Wired resilience normalization at runtime entry (`run_commander_runtime` start).

- File: `tests/test_m23_1_runtime_resilience_state_contract.py`
  - Added tests for:
    - default state injection
    - legacy-field normalization
    - commander runtime integration

## Safety Notes

- This is schema scaffolding only (additive).
- No execution guard/approval precedence changes.
- No order routing behavior changes.
