# M24-6: Guard Precedence Regression Bundle

- Date: 2026-02-17
- Goal: package M24 safety rules into one reproducible guard precedence check script.

## Scope (minimal)

1. Add one closeout-style script validating:
   - reject blocked after approved
   - executing-state block
   - duplicate claim block
   - explicit preflight denial code
2. Add pass/fail tests for the script.

## Implemented

- File: `scripts/run_m24_guard_precedence_check.py`
  - Deterministic checks:
    - strict reject guard after approved
    - executing-state approve block
    - duplicate claim block across two approval service instances
    - `RealExecutor.preflight_check` denial code check (`EXECUTION_DISABLED`)
  - Returns:
    - `0`: pass
    - `3`: fail

- File: `tests/test_m24_6_guard_precedence_check.py`
  - Added pass-case test.
  - Added fail-case test (`--skip-duplicate-case`).

## Safety Notes

- Script is regression tooling only.
- Core runtime behavior is unchanged in this milestone.
