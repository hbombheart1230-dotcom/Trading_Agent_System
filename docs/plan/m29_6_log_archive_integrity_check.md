# M29-6 Log Archive Integrity Check

- Date: 2026-02-21
- Goal: operationalize M29 archive governance with deterministic integrity + retention checks.

## What Was Added

1. Added `scripts/check_log_archive_integrity.py`.
   - Validates per-day archive bundle:
     - `archive/<day>/manifest.json`
     - file existence/hash/size/line_count verification
   - Validates retention policy:
     - detects stale archive day directories older than `retention_days`
   - Emits artifacts:
     - `log_archive_integrity_<day>.json`
     - `log_archive_integrity_<day>.md`

2. Added `scripts/run_m29_log_archive_integrity_check.py`.
   - Seeds pass/fail archive fixtures.
   - Runs integrity check in closeout style.
   - `--inject-fail` introduces:
     - tampered archive file (hash/size/line_count mismatch)
     - stale archive day beyond retention window

3. Added `tests/test_m29_7_log_archive_integrity_check.py`.
   - pass case
   - injected fail case
   - script entrypoint/import-resolution case

## Why This Matters

- Provides a concrete governance control for “archive integrity + retention” from M29 plan.
- Detects tampering/corruption and stale-retention drift before audit or recovery operations.
- Produces machine-readable artifacts for closeout and operator handover.
