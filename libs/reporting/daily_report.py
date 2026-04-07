from __future__ import annotations

import os
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


def build_separated_daily_report(daily_model: dict, *, model: str = None) -> dict:
    """Phase 6-1 Task 4: Fact/Narrative separated daily report."""
    from libs.reporting.fact_narrative_report import build_separated_report
    from libs.llm.model_names import normalize_openrouter_model_name
    chosen_model = normalize_openrouter_model_name(
        str(model or "").strip()
        or str(os.getenv("OPENROUTER_MODEL_REPORTER_FINAL", "")).strip()
        or str(os.getenv("OPENROUTER_DEFAULT_MODEL", "")).strip()
        or "openrouter/auto"
    )
    return build_separated_report(daily_model=daily_model, model=chosen_model)
