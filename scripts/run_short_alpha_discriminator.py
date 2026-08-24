from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.short_alpha_discriminator import write_short_alpha_discriminator


KST = timezone(timedelta(hours=9))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the read-only short-alpha discriminator package."
    )
    parser.add_argument(
        "--through-day",
        default=datetime.now(KST).date().isoformat(),
    )
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    day = args.through_day[:10]
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(args.reports_root) / "evaluation" / "short_alpha_discriminator" / day
    )
    result = write_short_alpha_discriminator(
        reports_root=Path(args.reports_root),
        through_day=day,
        output_dir=output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
