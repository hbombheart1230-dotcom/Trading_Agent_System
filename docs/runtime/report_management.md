# Report Management

## Canonical Directories

- `reports/daily`
- `reports/metrics`
- `reports/reconciliation`
- `reports/dev`
- `reports/milestones`

Operators should check the first four directories for day-to-day operations.
`reports/dev` is for diagnostics, replay, and deep analysis outputs.
`reports/milestones` is for M30/M31 evidence bundles.
For daily execution explainability, the official `trade_explain` output lives under `reports/dev/analysis/trade_explain/*`.
Top-level `reports/trade_explain/*` should be treated as legacy or ad-hoc output, not the canonical operator baseline.
Top-level `reports/operator_summary/*`, `reports/decision_story/*`, and `reports/run_cards/*` are deprecated residue and have been moved under `reports/_legacy_backup/report_surface_cleanup_2026-04-19/`.

Recommended `reports/dev` layout:

- `reports/dev/analysis`
  - `agent_pipeline_trace`
  - `trade_explain`  <- official daily trade-explain output path
  - `reporter_analysis`
  - `ops_diagnostic`
- `reports/dev/manual`
  - `decision_story`
  - `run_cards`
  - manual-only operator surfaces that should not recreate top-level `reports/decision_story` or `reports/run_cards`
  - closeout opt-in, validation-bundle, and maintenance/inventory flows should reference these paths
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
