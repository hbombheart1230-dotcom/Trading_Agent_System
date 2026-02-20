# M29-7 Incident Timeline Reconstruction Tooling

- Date: 2026-02-21
- Goal: reconstruct operator/audit-friendly incident timelines from event logs, including trigger->recovery (TTR) linkage.

## What Was Added

1. Added `scripts/reconstruct_incident_timeline.py`.
   - Inputs:
     - `--event-log-path`
     - `--report-dir`
     - `--day`
     - `--run-id`
     - `--window-before-sec`, `--window-after-sec`
     - `--require-incidents`
     - `--require-recovered`
   - Incident triggers:
     - `commander_router:error`
     - `commander_router:transition(transition=cooldown)`
     - `commander_router:resilience(reason=cooldown_active|incident_threshold_cooldown)`
     - `execute_from_packet:error`
   - Recovery markers:
     - `commander_router:intervention`
     - `commander_router:end(status=ok|resuming|normal)`
     - `commander_router:resilience(reason=cooldown_not_active|resume_applied|operator_resumed)`
     - `execute_from_packet:end`
   - Outputs:
     - `incident_timeline_<day>.json`
     - `incident_timeline_<day>.md`
   - Includes per-incident event slices and TTR summary (`avg/p50/p95/max`).

2. Added `scripts/run_m29_incident_timeline_check.py`.
   - Seeds deterministic pass/fail datasets.
   - Runs reconstruction with required incident + recovery gates.
   - `--inject-fail` creates unresolved incident paths.

3. Added `tests/test_m29_8_incident_timeline_check.py`.
   - pass case
   - injected fail case
   - script entrypoint/import-resolution case

## Why This Matters

- Converts raw JSONL logs into incident narratives that operators can review quickly.
- Provides measurable MTTR-like visibility (`time_to_recovery_sec`) for governance.
- Establishes a reproducible closeout gate for “incident timeline reconstruction” in M29.
