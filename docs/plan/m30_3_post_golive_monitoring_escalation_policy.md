# M30-3 Post-go-live Monitoring and Escalation Policy

- Date: 2026-02-21
- Goal: automate post-go-live monitoring policy activation from M30 sign-off status.

## What Was Added

1. Added `scripts/run_m30_post_golive_monitoring_policy.py`.
   - Inputs:
     - sign-off JSON artifact (`--signoff-json-path`) or
     - auto-run sign-off pipeline (`run_m30_release_signoff_checklist.py`)
   - Policy levels:
     - `normal`
     - `watch`
     - `incident`
   - Output artifacts:
     - `m30_post_golive_policy_<day>.json`
     - `m30_post_golive_policy_<day>.md`
   - Includes:
     - escalation level
     - active controls (`manual_approval_only`, heartbeat, alert fail-on level, on-call escalation)
     - monitoring target set for operations baseline

2. Added `tests/test_m30_3_post_golive_monitoring_policy.py`.
   - pass case
   - injected fail case
   - script entrypoint/import-resolution case

## Why This Matters

- Bridges final sign-off (`M30-2`) to runtime operating policy.
- Makes escalation behavior deterministic and auditable.
- Provides a direct handover artifact for post-go-live operations.
