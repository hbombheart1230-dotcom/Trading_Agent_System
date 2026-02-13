# Registry (JSONL) Design

## Sources
- `data/specs/kiwoom_api_list_tagged.jsonl`
- `data/specs/kiwoom_apis.jsonl`

## Rules
- **Primary key is `api_id`**
- `endpoint` duplication is expected → never identify an API by endpoint alone
- The entry like `api_id="공통"` (오류코드) is **catalog-only** (non-callable)

## Merge
Join by `api_id` to produce an internal `ApiSpec` object:
- from tagged: `category_major/minor`, `tags`
- from apis: `method`, `host{real/mock}`, `endpoint`, `request`, `response`, `examples`

## Runtime interface: ApiCatalog

- The runtime loader is `libs/api_catalog.py`.
- It normalizes JSON/JSONL/list/dict sources into an internal `ApiSpec`.
- This module is the **only** place that understands catalog loading rules.

### Why this matters
- Agents/skills/planners should depend on `ApiCatalog` interface, not raw JSONL files.
- Source format may evolve (Excel → JSONL → merged JSON), but callers stay stable.

- Canonical runtime catalog: `data/specs/api_catalog.jsonl`

---

## Status Snapshot (M2 complete)

- Canonical API catalog:
  - `data/specs/api_catalog.jsonl`
  - Built via `scripts/build_api_catalog.py`
  - Verified by pytest

- Source files are preserved and never read at runtime directly.
- Runtime components must depend on `ApiCatalog`, not raw JSONL files.

(M2 completed)
