# M31-1: SLO Baseline and Incident Review Workflow

- Date: 2026-02-21
- Goal: establish post-go-live stabilization workflow with explicit SLO baseline, severity ladder, and recurring incident review loop.
- Scope: operations workflow and measurement policy (no re-implementation of M30 signoff/policy logic).

## Inputs (Consume, Do Not Rebuild)

1. M30 final signoff artifact
- source: `scripts/run_m30_final_golive_signoff.py`
- artifact: `m30_final_golive_signoff_<day>.json|md`

2. M30 post-go-live policy artifact
- source: `scripts/run_m30_post_golive_monitoring_policy.py`
- artifact: `m30_post_golive_policy_<day>.json|md`

3. Daily metrics/governance artifacts
- source: `scripts/generate_metrics_report.py`
- source: `scripts/run_m29_closeout_check.py`

## SLO Baseline (Initial)

1. Availability
- definition: successful run cycles / scheduled run cycles
- initial target: `>= 99%` daily

2. Latency
- definition: runtime hot-path latency p95 (execution boundary)
- initial target: p95 within current M30 green baseline + controlled drift

3. Error budget
- definition: allowed daily failure envelope from incidents + critical alerts
- initial target: measurable daily consumption, no untracked burn

4. Safety floor (non-negotiable)
- duplicate execution: `0`
- guard precedence violation: `0`
- mock/real mode leakage: `0`

## Severity Ladder (On-call)

1. `SEV-1`
- customer/system safety at risk, execution must be constrained immediately
- action: force manual approval + degrade mode + primary/secondary escalation

2. `SEV-2`
- major functionality impaired, controlled workaround exists
- action: primary escalation + mitigation within same session

3. `SEV-3`
- partial degradation or noisy alerts without safety breach
- action: ticket + next review window fix

## Daily Workflow (KST)

1. Pre-open check
- verify latest M30 policy artifact level (`normal/watch/incident`)
- verify startup preflight and guard config alignment

2. Session monitoring
- track SLO probes (availability/latency/error budget)
- record intervention decisions with reason codes

3. Post-close review
- generate daily metrics snapshot
- classify incidents by severity
- produce one daily stabilization summary

## Weekly Incident Review Loop

1. Inputs
- 5 trading-day metrics snapshots
- incident timeline and intervention logs
- unresolved alert inventory

2. Required outputs
- top recurring failure classes (Top N)
- false-positive and duplicate alert reduction actions
- runbook changes with owner + due date
- SLO target/threshold adjustment decision (if needed)

## Recurring Postmortem Template (Minimal)

1. Event summary
- incident id, time window, severity, impacted scope

2. Detection and response
- first signal source, detection delay, mitigation timeline

3. Root cause and contributing factors
- technical root cause
- process/policy factors

4. Corrective actions
- immediate guard changes
- medium-term engineering tasks
- prevention checks and acceptance criteria

5. Ownership and follow-up
- action owner
- due date
- verification evidence path

## Operator Command Reference

```bash
python scripts/run_m30_final_golive_signoff.py --json
python scripts/run_m30_post_golive_monitoring_policy.py --json
python scripts/run_m29_closeout_check.py --json

set EVENT_LOG_PATH=./data/logs/events.jsonl
set REPORT_DIR=./reports
set METRICS_DAY=2026-02-21
python scripts/generate_metrics_report.py
```

## Execution Artifact (Implemented)

- script: `scripts/run_m31_slo_incident_review_check.py`
- role: consumes M30 artifacts + event log and emits a daily M31-1 stabilization check artifact.
- output:
  - `reports/m31_slo_incident/m31_slo_incident_<day>.json`
  - `reports/m31_slo_incident/m31_slo_incident_<day>.md`

```bash
python scripts/run_m31_slo_incident_review_check.py \
  --event-log-path data/logs/events.jsonl \
  --policy-report-dir reports/m30_post_golive \
  --signoff-report-dir reports/m30_golive \
  --report-dir reports/m31_slo_incident \
  --day 2026-02-21 \
  --json
```

## Exit Criteria (M31-1 Complete)

- SLO baseline and severity ladder are versioned in docs.
- daily and weekly review loop is executable without ad-hoc interpretation.
- incident ownership and escalation path are deterministic from artifacts.
