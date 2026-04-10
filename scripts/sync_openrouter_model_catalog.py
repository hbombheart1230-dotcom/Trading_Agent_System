from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.llm.model_catalog_store import DEFAULT_CATALOG_DIR, sync_openrouter_model_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch OpenRouter model metadata and build local model cards.")
    parser.add_argument("--catalog-dir", default=str(DEFAULT_CATALOG_DIR), help="Target catalog directory")
    parser.add_argument("--timeout-sec", type=float, default=20.0, help="OpenRouter fetch timeout in seconds")
    parser.add_argument("--no-cache-fallback", action="store_true", help="Fail instead of using cached raw model list")
    args = parser.parse_args()

    result = sync_openrouter_model_catalog(
        catalog_dir=Path(str(args.catalog_dir)),
        timeout_sec=float(args.timeout_sec),
        allow_cached_fallback=not bool(args.no_cache_fallback),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
