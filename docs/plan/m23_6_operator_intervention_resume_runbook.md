# M23-6: Operator Intervention and Resume Runbook

- Date: 2026-02-17
- Goal: define and implement a safe operator intervention path to resume runtime from cooldown/degrade state.

## Scope (minimal)

1. Add explicit operator runtime control for resume (`runtime_control=resume`).
2. When resume is requested, clear commander cooldown/degrade incident state in one place.
3. Emit auditable intervention event for operator actions.
4. Document runbook steps for intervention and resume.

## Implemented

- File: `graphs/commander_runtime.py`
  - Added `resume` transition support in runtime control normalization.
  - Added `_apply_operator_resume_intervention(...)`:
    - clears:
      - `resilience.degrade_mode`
      - `resilience.degrade_reason`
      - `resilience.incident_count`
      - `resilience.cooldown_until_epoch`
      - `resilience.last_error_type`
    - returns structured intervention payload for audit
  - Wired intervention flow before cooldown guard:
    - logs `stage=commander_router`, `event=intervention`
    - allows runtime path to continue after explicit operator resume

- File: `scripts/run_commander_runtime_once.py`
  - Added CLI choice `--runtime-control resume` for operator smoke/demo.

- File: `tests/test_m23_6_operator_intervention_resume.py`
  - Added tests for:
    - cooldown/degrade state is cleared and runtime continues when `resume` is requested
    - runtime once CLI accepts `resume` and reports transition/status

## Runbook (operator)

1. Confirm incident and cooldown status from runtime/event logs.
2. Verify upstream stability and guard settings (`EXECUTION_ENABLED`, allowlist, limits).
3. Execute controlled resume using `runtime_control=resume`.
4. Confirm intervention event was logged (`commander_router/intervention`).
5. Monitor the next run for fresh incidents before restoring normal operating cadence.

## Safety Notes

- Resume is explicit (no automatic cooldown bypass).
- Intervention is auditable via structured event logging.
- Normal routing remains unchanged when `runtime_control` is not `resume`.
