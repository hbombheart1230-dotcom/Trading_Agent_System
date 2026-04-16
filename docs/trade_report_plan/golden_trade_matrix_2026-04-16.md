# Golden Trade Matrix (2026-04-16)

## Goal

Define a fixed set of representative trade cases that must be used for report regression checks.

This matrix prevents helper-only testing from hiding runtime regressions.

## Required Case Types

### Case 1. Normal Closed Trade

Purpose:

- baseline healthy lifecycle
- confirms end-to-end report generation on a normal entry-hold-exit flow

Required properties:

- entry run id exists
- hold events exist or hold duration is computed from entry/exit timestamps
- exit reason exists
- selected rank and candidate count are non-zero

### Case 2. Short Hold Closed Trade

Purpose:

- validates very short duration trades
- ensures short holds do not collapse to fake `00:00:00`

Required properties:

- hold duration is short but real
- monitor snapshots may be thin
- report still explains why exit happened

### Case 3. Partial Recovery Trade

Purpose:

- validates sell-side recovery and incomplete lifecycle handling
- confirms the system marks partial recovery honestly

Required properties:

- partial or recovered trade origin
- explicit recovery metadata
- no fake completeness
- no misleading provenance

### Case 4. Reporter Missing Trade

Purpose:

- validates same-day reporter linkage honesty
- ensures missing reporter analysis does not look linked

Required properties:

- `same_day_reporter_linkage.status=missing` or explicit day fallback
- expected reporter path may exist as metadata
- actual artifact path must be empty when file is absent

### Case 5. Scanner-Strong Trade

Purpose:

- validates rich scanner-selected quality output
- confirms selected symbol, rank, score drivers, and runner-up comparison survive to report input

Required properties:

- selected symbol present
- selected rank > 0
- candidate count > 0
- score drivers populated

### Case 6. Entry-Recovered But Thin Trade

Purpose:

- validates recovered entry context without over-claiming execution evidence
- confirms trade remains diagnosable without pretending completeness

Required properties:

- recovered entry reason may exist
- entry execution evidence must be called thin or partial when run id and ts are absent
- hold duration must remain blank, not fabricated

## Current Recommended Real Cases

### `TRD_20260415_000660_04`

Use for:

- baseline closed trade
- report wording quality
- strategist/scanner/entry/hold/exit narrative quality
- authoritative closed-trade consistency between `lifecycle_bundle.json`, `_health.json`, `_provenance.json`, and `ai_trade_report_input.json`

### `TRD_20260416_000660_01`

Use for:

- targeted repair validation
- short-hold closed trade
- bundle replay integrity
- selected symbol/rank propagation

### `TRD_20260416_047040_01`

Use for:

- second repaired trade with distinct scanner details
- short-hold closed trade validation
- compare selected candidate propagation across a separate symbol

## Known Non-Golden Example

### `TRD_20260415_000660_01`

Do not use this as a default runtime golden.

Reason:

- stale alias / remapped trade directory symptoms were observed
- `lifecycle_bundle.json`, `_health.json`, `_provenance.json`, and `ai_trade_report_input.json` do not agree on open vs closed state
- useful as a status-conflict audit sample, but not as a baseline acceptance case

## Per-Case Assertion Checklist

For every golden case, verify at minimum:

1. `entry.json`
- `run_id`
- `ts`
- `reason_human`
- selected symbol/rank where applicable

2. `hold.json`
- `hold_duration`
- `hold_duration_sec`
- `holding_phase_summary`
- `hold_events_count`

3. `exit.json`
- `run_id`
- `ts`
- `reason_human`
- `execution_details`

4. `lifecycle_bundle.json`
- `trade_origin`
- `lifecycle_completeness`
- `linked_run_ids`
- `same_day_reporter_linkage`
- `failure_classification`

5. `ai_trade_report_input.json`
- selected symbol/rank
- candidate count
- hold duration
- execution details
- section provenance

6. `ai_trade_report.json`
- generation status
- key section summaries present
- provenance does not collapse incorrectly

7. `ai_trade_report.md`
- explains entry
- explains hold
- explains exit
- identifies likely failure axis

## Update Policy

Do not replace a golden case casually.

Only update the matrix when:

- the runtime path changed materially
- a case became permanently obsolete
- a better representative real trade is available

When adding a new case:

- state why it exists
- state which failure mode it protects against
- add at least one chain-level acceptance assertion

## Operational Rule

Any report patch that changes lifecycle assembly, provenance, or report section merge rules must be checked against at least:

1. one baseline normal closed trade
2. one short-hold repaired trade
3. one reporter-missing or partial-recovery trade
4. one authoritative status-consistency case
