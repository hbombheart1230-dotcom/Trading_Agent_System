# M26-6: Closeout and M27 Handover

- Date: 2026-02-20
- Goal: finalize M26 evaluation baseline with one reproducible closeout gate and hand over to M27.

## Scope (minimal)

1. Add one closeout script that validates end-to-end M26 stack:
   - M26-1 dataset manifest scaffold
   - M26-2 replay runner
   - M26-3 scorecard metrics
   - M26-4 A/B evaluation
   - M26-5 promotion gate check
2. Add pass/fail tests for closeout behavior.
3. Mark roadmap/index/tree for M26-6 handover status.

## Implemented

- File: `scripts/run_m26_closeout_check.py`
  - Seeds baseline and candidate datasets via M26-1 scaffold.
  - Applies candidate upgrade scenario for deterministic A/B superiority.
  - Executes M26-2/3/4/5 scripts in JSON mode.
  - Validates:
    - each step `rc == 0` and `ok == true`
    - A/B winner is `candidate`
    - promotion gate recommendation is `promote_candidate`
  - Supports failure injection with `--inject-gate-fail`.
  - Returns:
    - `0`: pass
    - `3`: fail

- File: `tests/test_m26_6_closeout_check.py`
  - Added pass-case closeout test.
  - Added fail-case test using `--inject-gate-fail`.
  - Added script entrypoint import-resolution regression test.

## Handover Notes (to M27)

- M26 now has baseline evaluation flow:
  - fixed dataset contract
  - replay timeline
  - scorecard metrics
  - A/B comparison
  - promotion gate thresholding
- M27 can start from this foundation to add:
  - multi-strategy allocation policies
  - conflict resolution under concurrent intents
  - portfolio-level risk budget simulation gates

## Safety Notes

- This milestone is evaluation tooling only and does not alter live execution behavior.
