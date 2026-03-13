# Report Management

## Canonical Directories

- `reports/daily`
- `reports/metrics`
- `reports/operator_summary`
- `reports/decision_story`
- `reports/run_cards`
- `reports/reconciliation`
- `reports/dev`
- `reports/milestones`

Operators should check the first six directories for day-to-day operations.
`reports/dev` is for diagnostics, replay, and deep analysis outputs.
`reports/milestones` is for M30/M31 evidence bundles.

Recommended `reports/dev` layout:

- `reports/dev/analysis`
  - `agent_pipeline_trace`
  - `trade_explain`
  - `reporter_analysis`
  - `ops_diagnostic`
- `reports/dev/live`
  - `live_summary`
  - `live_watch`
- `reports/dev/exam`
  - `mock_exam_day`
- `reports/dev/catalog`
  - report inventory snapshots

## Non-Canonical / Archive Candidates

- `reports/offhours_*`
  - one-off strategy/debug experiment bundles
  - archived under `reports/archive/experiments/offhours/`
- `reports/m22_*`, `reports/m23_*`, `reports/m25_*`, `reports/m28_*`
  - historical milestone validation artifacts
  - should live under `reports/milestones/`
- `reports/daily_test`
  - test-only output
- root `reports/daily_report_<day>.md|json`
  - legacy duplicate format
  - should be migrated into canonical `reports/daily/daily_<day>.md|json`

These should not remain mixed into the main operator view indefinitely.

## Inventory / Cleanup Command

Inspect only:

```bash
python -m scripts.run_report_maintenance --report-root reports --event-log-path data/logs/events.jsonl --json
```

Inspect and archive obvious experiment clutter:

```bash
python -m scripts.run_report_maintenance --report-root reports --event-log-path data/logs/events.jsonl --apply --json
```

Archive legacy root-level daily reports too:

```bash
python -m scripts.run_report_maintenance --report-root reports --event-log-path data/logs/events.jsonl --apply --include-legacy-root-daily --json
```

Archive legacy milestone directories too:

```bash
python -m scripts.run_report_maintenance --report-root reports --event-log-path data/logs/events.jsonl --apply --include-legacy-milestones --json
```

Archive both legacy daily files and legacy milestone directories:

```bash
python -m scripts.run_report_maintenance --report-root reports --event-log-path data/logs/events.jsonl --apply --include-legacy-root-daily --include-legacy-milestones --json
```

## Inventory Artifacts

- `reports/dev/catalog/report_inventory_latest.md`
- `reports/dev/catalog/report_inventory_latest.json`

Closeout orchestration now generates the inventory automatically as a non-destructive step.
