from __future__ import annotations

from pathlib import Path
from typing import Tuple


def generate_daily_report(events_path: Path, out_dir: Path, day: str) -> Tuple[Path, Path]:
    """Delegate to the canonical daily-report generator used by current scripts.

    This keeps older runtime call sites compatible while ensuring that the live
    EOD pipeline writes the richer canonical reports/daily payload instead of the
    older minimal summary format.
    """

    from scripts.generate_daily_report import generate_daily_report as canonical_generate_daily_report

    return canonical_generate_daily_report(events_path, out_dir, day=day)
