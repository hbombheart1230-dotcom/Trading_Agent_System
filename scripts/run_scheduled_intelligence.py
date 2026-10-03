from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.scheduled_intelligence import materialize_preopen_intelligence


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize scheduled intelligence artifacts without trading behavior changes.")
    parser.add_argument("--phase", choices=["preopen"], required=True)
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--capture-rc", type=int, default=0)
    parser.add_argument("--session-rc", type=int, default=0)
    parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = materialize_preopen_intelligence(day=args.day, capture_rc=args.capture_rc, session_rc=args.session_rc, reports_root=args.reports_root)
    if args.json: print(json.dumps(payload, ensure_ascii=False, indent=2))
    else: print(f"status={payload['status']} manifest={payload['manifest_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
