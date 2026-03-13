# Log Management

`data/logs/` is now grouped the same way as `reports/`.

## Canonical Layout

- core:
  - `data/logs/events.jsonl`
  - `data/logs/intents.jsonl`
- dev:
  - `data/logs/dev/analysis/offhours/`
  - `data/logs/dev/live/`
  - `data/logs/dev/session/`
  - `data/logs/dev/testing/`
  - `data/logs/dev/catalog/`
- milestones:
  - `data/logs/milestones/m22/`
  - `data/logs/milestones/m23/`
  - `data/logs/milestones/m24/`
  - `data/logs/milestones/m25/`
  - `data/logs/milestones/m27/`
  - `data/logs/milestones/m30/`

## Operator Rule

- only `events.jsonl` and `intents.jsonl` are canonical live runtime logs
- `dev/*` holds debugging, smoke, live-session helper, and off-hours validation logs
- `milestones/*` holds historical stage evidence

## Maintenance

Inspect current layout:

```powershell
python -m scripts.run_log_maintenance --log-root data/logs --json
```

Apply canonical moves:

```powershell
python -m scripts.run_log_maintenance --log-root data/logs --apply --json
```

Inventory output:

- `data/logs/dev/catalog/log_inventory_latest.md`
- `data/logs/dev/catalog/log_inventory_latest.json`
