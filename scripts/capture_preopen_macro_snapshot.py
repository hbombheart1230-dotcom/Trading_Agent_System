from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.market.preopen_macro_snapshot import capture_preopen_macro_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture macro/index evidence before market open.")
    parser.add_argument("--env-path", type=Path, default=ROOT / ".env")
    parser.add_argument("--state-path", type=Path, default=ROOT / "data" / "state.json")
    args = parser.parse_args()
    os.chdir(ROOT)
    result = capture_preopen_macro_snapshot(
        env_path=args.env_path,
        state_path=args.state_path,
    )
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result.get("status") in {"ok", "fallback"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
