from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from libs.llm.model_catalog import resolve_policy_llm_execution_slot, resolve_policy_llm_slot


def generate_daily_report(events_path: Path, out_dir: Path, day: str) -> Tuple[Path, Path]:
    """Delegate to the canonical daily-report generator used by current scripts.

    This keeps older runtime call sites compatible while ensuring that the live
    EOD pipeline writes the richer canonical reports/operator_summary/daily
    payload instead of the older minimal summary format.
    """

    from scripts.generate_daily_report import generate_daily_report as canonical_generate_daily_report

    return canonical_generate_daily_report(events_path, out_dir, day=day)


def build_separated_daily_report(daily_model: dict, *, model: str = None) -> dict:
    """Phase 6-1 Task 4: Fact/Narrative separated daily report."""
    from libs.reporting.fact_narrative_report import build_separated_report
    from libs.llm.model_names import normalize_openrouter_model_name
    llm_slot = resolve_policy_llm_slot(daily_model if isinstance(daily_model, dict) else {}, "reporter", "daily", default_profile="strong_reasoning")
    execution_profile = resolve_policy_llm_execution_slot(
        daily_model if isinstance(daily_model, dict) else {},
        "reporter",
        "daily",
        default_profile="deep_review",
        defaults={
            "profile_name": "deep_review",
            "name": "deep_review",
            "temperature": 0.2,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry": {"max_attempts": 2, "backoff_sec": 0.0},
            "retry_max": 2,
            "retry_backoff_sec": 0.0,
        },
    )
    chosen_model = normalize_openrouter_model_name(
        str(model or "").strip()
        or str(llm_slot.get("primary") or "").strip()
        or "moonshotai/kimi-k2.5"
    )
    return build_separated_report(
        daily_model=daily_model,
        model=chosen_model,
        execution_profile=execution_profile,
    )
