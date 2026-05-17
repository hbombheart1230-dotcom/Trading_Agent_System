from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.catalog.api_catalog_builder import (  # noqa: E402
    INPUT_FILES,
    OUTPUT_FILE,
    build_api_catalog,
    load_jsonl,
    main,
    merge_records,
)


if __name__ == "__main__":
    main()
