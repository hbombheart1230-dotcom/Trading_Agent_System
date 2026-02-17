# M23-4: Commander Incident Counter and Cooldown Routing

- Date: 2026-02-17
- Goal: enforce incident-count and cooldown policy in commander routing before runtime path execution.

## Scope (minimal)

1. Add commander-level cooldown guard using `state["resilience"]`:
   - block run while cooldown is active
   - open cooldown when incident threshold is reached
2. Register commander incident when runtime path raises an exception.
3. Keep default behavior backward-compatible (policy disabled by default).

## Implemented

- File: `graphs/commander_runtime.py`
  - Added policy helpers:
    - `_resolve_commander_cooldown_policy(...)`
    - `_apply_commander_cooldown_guard(...)`
    - `_register_commander_incident(...)`
  - Added cooldown short-circuit path:
    - sets `runtime_status="cooldown_wait"`
    - sets `runtime_transition="cooldown"`
    - logs `commander_router` events (`transition`, `resilience`, `end`)
  - Added runtime exception incident handling:
    - increments `resilience.incident_count`
    - updates `resilience.last_error_type`
    - opens cooldown when threshold/cooldown policy is met
    - logs `commander_router/error` and re-raises exception
  - Policy sources:
    - `state["resilience_policy"]` (`incident_threshold`, `cooldown_sec`)
    - env fallback (`COMMANDER_INCIDENT_THRESHOLD`, `COMMANDER_COOLDOWN_SEC`)

- File: `tests/test_m23_4_commander_incident_cooldown_routing.py`
  - Added tests for:
    - cooldown-active block
    - threshold-triggered cooldown open
    - exception-driven incident increment and error event logging

## Safety Notes

- Policy defaults are disabled (`threshold=0`, `cooldown=0`) to preserve legacy behavior.
- No execution guard precedence changes.
- No order routing behavior changes.
