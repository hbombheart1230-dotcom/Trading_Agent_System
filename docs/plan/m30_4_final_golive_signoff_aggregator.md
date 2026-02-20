# M30-4 Final Go-live Signoff Aggregator

- Date: 2026-02-21
- Goal: produce one final go-live decision artifact by chaining M30-1/2/3 outputs.

## What Was Added

1. Added `scripts/run_m30_final_golive_signoff.py`.
   - Sequentially runs:
     - `run_m30_quality_gates_bundle.py` (M30-1)
     - `run_m30_release_signoff_checklist.py` (M30-2)
     - `run_m30_post_golive_monitoring_policy.py` (M30-3)
   - Emits final decision:
     - `approve_go_live`
     - `hold_go_live`
   - Output artifacts:
     - `m30_final_golive_signoff_<day>.json`
     - `m30_final_golive_signoff_<day>.md`
   - Supports `--inject-fail` for red-path verification.

2. Added `tests/test_m30_4_final_golive_signoff.py`.
   - pass case
   - injected fail case
   - script entrypoint/import-resolution case

## Why This Matters

- Consolidates M30 readiness into one auditable decision output.
- Makes release approval deterministic and repeatable.
- Provides direct operator handover evidence for go-live gate review.
