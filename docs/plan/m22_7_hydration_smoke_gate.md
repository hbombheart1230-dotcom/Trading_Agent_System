# M22-7: Hydration Smoke Gate Script

- Date: 2026-02-16
- Goal: provide an operator-facing smoke gate that validates graph hydration behavior in normal and timeout scenarios.

## Scope (minimal)

1. Add smoke script with pass/fail conditions for hydration and fallback.
2. Support both normal and timeout simulation runs.
3. Add automated tests for smoke gate return codes.

## Implemented

- File: `scripts/smoke_m22_hydration.py`
  - Added flags:
    - `--simulate-timeout`
    - `--require-skill-fetch`
    - `--require-fallback`
    - `--require-no-fallback`
    - `--show-json`
  - Exit code policy:
    - `0`: gate passed
    - `3`: one or more requirements failed

- File: `tests/test_m22_7_hydration_smoke_script.py`
  - Added tests for:
    - normal run + no-fallback requirement
    - timeout run + fallback requirement
    - expected failure when timeout run requires no fallback

## Safety Notes

- Script uses demo-safe runner and does not place orders.
- Gate is additive and does not change runtime behavior.
