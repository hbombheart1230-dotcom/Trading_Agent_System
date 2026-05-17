from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.agent.reporter import Reporter  # noqa: E402
from libs.reporting.daily_report_generator import generate_daily_report as _generate_daily_report  # noqa: E402


def generate_daily_report(events_path: Path, out_dir: Path, day: Optional[str] = None) -> Tuple[Path, Path]:
    return _generate_daily_report(events_path, out_dir, day=day)


def main() -> None:
    events_path = Path(os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl"))
    out_dir = Path(os.getenv("REPORT_DIR", "./reports"))
    day = os.getenv("REPORT_DAY")
    result = Reporter().generate_daily_report(
        event_log_path=events_path,
        reports_root=out_dir,
        day=day,
    )
    print(f"Wrote: {result.report_md_path}")
    print(f"Wrote: {result.report_json_path}")


if __name__ == "__main__":
    main()
