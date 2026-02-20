# M30-2 Release Sign-off Checklist

- Date: 2026-02-21
- Goal: generate one release sign-off checklist artifact for architecture/security/operations based on M30 quality-gate evidence.

## What Was Added

1. Added `scripts/run_m30_release_signoff_checklist.py`.
   - Input modes:
     - consume existing quality bundle json (`--quality-gates-json-path`)
     - or execute `run_m30_quality_gates_bundle.py` automatically
   - Produces sign-off artifacts:
     - `m30_release_signoff_<day>.json`
     - `m30_release_signoff_<day>.md`
   - Required checklist categories:
     - architecture
     - security
     - operations
   - Final decision field:
     - `release_ready` (`true` only when all required checks pass)

2. Added `tests/test_m30_2_release_signoff_checklist.py`.
   - pass case
   - injected fail case
   - script entrypoint/import-resolution case

## Why This Matters

- Converts quality-gate outputs into a formal release decision artifact.
- Keeps sign-off criteria explicit, reproducible, and machine-readable.
- Aligns directly with M30 deliverable: release sign-off checklist (architecture/security/operations).
