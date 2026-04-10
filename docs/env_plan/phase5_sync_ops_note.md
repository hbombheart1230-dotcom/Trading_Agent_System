# Phase 5 Sync Ops Note

## Sync script
Use:

```powershell
venv\Scripts\python.exe scripts\sync_openrouter_model_catalog.py
```

Optional flags:

```powershell
venv\Scripts\python.exe scripts\sync_openrouter_model_catalog.py --catalog-dir data/model_catalog --timeout-sec 20
venv\Scripts\python.exe scripts\sync_openrouter_model_catalog.py --no-cache-fallback
```

## What it writes
- `data/model_catalog/openrouter_models.json`
- `data/model_catalog/model_cards.json`

## Cached fallback behavior
If the OpenRouter fetch fails:
- and a previous `openrouter_models.json` exists
- the script uses that cached raw snapshot
- then rebuilds `model_cards.json` from the cached snapshot

The returned result surface marks this via:
- `fetch_source = "cached_fallback"`

If `--no-cache-fallback` is supplied, fetch failure becomes a hard error.

## Scheduling status
Scheduling is intentionally **not** set up yet.

This phase only provides:
- a manual sync command
- local snapshot persistence
- deterministic card generation

It does **not** add:
- cron/task scheduling
- runtime auto-refresh
- Commander/Strategist/Reporter integration

## Operational note
This catalog layer is currently safe because it is data-only.
Refreshing the catalog does not change:
- active runtime behavior
- model routing
- execution profile selection
- trading semantics
