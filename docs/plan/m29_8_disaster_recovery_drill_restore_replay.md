# M29-8 Disaster Recovery Drill (Restore + Replay Validation)

- Date: 2026-02-21
- Goal: run a deterministic DR drill that proves archived artifacts can restore runtime data and reproduce replay metrics.

## What Was Added

1. Added `scripts/run_m29_disaster_recovery_drill.py`.
   - End-to-end flow:
     - seed working dataset
     - run baseline replay
     - snapshot into archive day folder
     - build archive manifest (hash/bytes/line_count)
     - run archive integrity check (`check_log_archive_integrity.py`)
     - simulate working storage loss
     - restore dataset from archive snapshot
     - run replay on restored dataset
     - validate replay parity (`baseline` vs `restored`)
   - Supports `--inject-fail`:
     - tampers archived fill log after manifest creation
     - forces integrity mismatch and replay parity mismatch

2. Added `tests/test_m29_9_disaster_recovery_drill.py`.
   - pass case
   - injected fail case
   - script entrypoint/import-resolution case

## Why This Matters

- Implements M29 requirement for disaster recovery drill with measurable checks.
- Verifies both:
  - artifact integrity (tamper/corruption detection)
  - functional recoverability (restored replay equals baseline replay)
- Produces closeout-friendly JSON summary for operator handover.
