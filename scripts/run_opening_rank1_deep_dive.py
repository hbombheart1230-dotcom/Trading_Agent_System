from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.opening_rank1_deep_dive import run_opening_rank1_deep_dive


if __name__ == "__main__":
    print(json.dumps(run_opening_rank1_deep_dive(), ensure_ascii=False, indent=2))
