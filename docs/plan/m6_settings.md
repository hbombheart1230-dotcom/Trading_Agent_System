# M6-0 – Settings Loader

## Purpose
Centralize environment variables into a single `Settings` object before introducing real HTTP calls.

## Outputs
- `libs/settings.py` provides:
  - `load_env_file()` (minimal .env parser, no external deps)
  - `Settings.from_env()` (normalized config + defaults)
  - `Settings.base_url` (mode-based URL selection)

## Notes
- `.env` should include your own `KIWOOM_APP_KEY` / `KIWOOM_APP_SECRET`.
- Canonical catalog path key (recommended):
  - `KIWOOM_API_CATALOG_PATH=./data/specs/api_catalog.jsonl`
