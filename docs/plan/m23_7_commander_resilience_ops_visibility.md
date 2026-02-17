# M23-7: Commander Resilience Ops Visibility Script

- Date: 2026-02-17
- Goal: provide an operator-friendly CLI to inspect commander resilience/cooldown/intervention events from `events.jsonl`.

## Scope (minimal)

1. Add a dedicated ops query CLI for `stage=commander_router` resilience events.
2. Support incident-only filtering for cooldown/error triage.
3. Provide both human-readable and JSON output for manual ops and automation.

## Implemented

- File: `scripts/query_commander_resilience_events.py`
  - Reads event log JSONL (`--path`, default `EVENT_LOG_PATH`).
  - Filters commander events with options:
    - `--run-id`
    - `--only-incidents`
    - `--include-route`
    - `--limit`
    - `--json`
  - Incident classification includes:
    - `event=error`
    - `event=transition` with `transition=cooldown`
    - `event=resilience` with reason `cooldown_active|incident_threshold_cooldown`
  - Outputs summary fields:
    - `event_total`
    - `cooldown_transition_total`
    - `intervention_total`
    - `error_total`
    - `latest_status`, `latest_run_id`

- File: `tests/test_m23_7_commander_resilience_ops_script.py`
  - Added tests for:
    - missing path error code
    - incident-only JSON filtering behavior
    - run-id filtering and human-readable summary output

## Operator Usage

```bash
python scripts/query_commander_resilience_events.py --path data/logs/events.jsonl --only-incidents
python scripts/query_commander_resilience_events.py --path data/logs/events.jsonl --run-id <RUN_ID> --json
```

## Safety Notes

- Observability-only change: no runtime decision or execution behavior modified.
- Script is read-only against event logs.
