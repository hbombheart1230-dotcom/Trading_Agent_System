from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .cohorts import (
    build_cohort_review,
    independent_day_symbol_rows,
    join_opening_to_feature_mart,
)
from .contracts import BEHAVIOR_EFFECT, PRIMARY_COHORT_ID, SCHEMA_VERSION
from .profit_lock import build_profit_fade_review
from .report import render_short_alpha_discriminator
from .scanner_diagnostics import build_scanner_diagnostics
from .strategist_roi import build_strategist_stage2_review


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {"path": str(path), "available": path.exists(), "error": None}
    if not path.exists():
        source["error"] = "MISSING_ARTIFACT"
        return {}, source
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        source["error"] = f"INVALID_ARTIFACT:{type(exc).__name__}"
        return {}, source
    if not isinstance(payload, Mapping):
        source["error"] = "SCHEMA_MISMATCH:ROOT_NOT_OBJECT"
        return {}, source
    source["schema_version"] = payload.get("schema_version")
    return dict(payload), source


def _latest_cumulative_agent_scorecard(reports_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = reports_root / "evaluation" / "agent_effectiveness"
    paths = sorted(root.glob("cumulative_*/agent_effectiveness_scorecard.json"))
    if not paths:
        return {}, {"path": str(root), "available": False, "error": "MISSING_ARTIFACT"}
    return _load_json(paths[-1])


def build_short_alpha_discriminator(
    *, reports_root: Path, through_day: str
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    opening, opening_source = _load_json(
        reports_root
        / "evaluation"
        / "opening_rank1_shadow"
        / "opening_rank1_shadow_cumulative.json"
    )
    feature_mart, feature_source = _load_json(
        reports_root
        / "evaluation"
        / "feature_mart"
        / "opening_rank1"
        / "feature_mart.json"
    )
    agent_scorecard, scorecard_source = _latest_cumulative_agent_scorecard(reports_root)
    joined, join_integrity = join_opening_to_feature_mart(
        [row for row in opening.get("episodes") or [] if isinstance(row, Mapping)],
        [row for row in feature_mart.get("episodes") or [] if isinstance(row, Mapping)],
    )
    cohort_review = build_cohort_review(joined)
    primary_rows = independent_day_symbol_rows(
        [
            row
            for row in joined
            if row.get("asset_class") == "common_stock"
            and row.get("risk_band") == "HIGH"
        ]
    )
    source_errors = [
        source.get("error")
        for source in (opening_source, feature_source, scorecard_source)
        if source.get("error")
    ]
    if opening_source.get("error") or feature_source.get("error"):
        status = "INVALID_REQUIRED_SOURCE"
    elif join_integrity.get("missing_join_count"):
        status = "PASS_WITH_JOIN_GAPS"
    elif scorecard_source.get("error"):
        status = "PASS_WITH_OPTIONAL_SOURCE_GAP"
    else:
        status = "PASS"
    return {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": BEHAVIOR_EFFECT,
        "through_day": through_day[:10],
        "primary_candidate_id": PRIMARY_COHORT_ID,
        "integrity": {
            "status": status,
            "source_errors": source_errors,
            "join": join_integrity,
        },
        "sources": {
            "opening_rank1": opening_source,
            "feature_mart": feature_source,
            "agent_effectiveness": scorecard_source,
        },
        "cohort_review": cohort_review,
        "profit_fade_review": build_profit_fade_review(primary_rows),
        "scanner_diagnostics": build_scanner_diagnostics(joined),
        "strategist_stage2_review": build_strategist_stage2_review(
            [row for row in feature_mart.get("episodes") or [] if isinstance(row, Mapping)],
            agent_scorecard,
        ),
        "behavior_change_authorized": False,
    }


def write_short_alpha_discriminator(
    *, reports_root: Path, through_day: str, output_dir: Path
) -> dict[str, Any]:
    payload = build_short_alpha_discriminator(
        reports_root=Path(reports_root), through_day=through_day
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_json_path": output_dir / "short_alpha_discriminator.json",
        "summary_markdown_path": output_dir / "short_alpha_discriminator.md",
        "cohort_json_path": output_dir / "short_alpha_cohorts.json",
        "profit_fade_json_path": output_dir / "profit_fade_shadow.json",
        "strategist_roi_json_path": output_dir / "strategist_stage2_roi.json",
        "scanner_diagnostics_json_path": output_dir / "scanner_diagnostics.json",
    }
    paths["summary_json_path"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["summary_markdown_path"].write_text(
        render_short_alpha_discriminator(payload), encoding="utf-8"
    )
    paths["cohort_json_path"].write_text(
        json.dumps(payload["cohort_review"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["profit_fade_json_path"].write_text(
        json.dumps(payload["profit_fade_review"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["strategist_roi_json_path"].write_text(
        json.dumps(payload["strategist_stage2_review"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["scanner_diagnostics_json_path"].write_text(
        json.dumps(payload["scanner_diagnostics"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **{key: str(value) for key, value in paths.items()},
        "integrity_status": payload["integrity"]["status"],
        "behavior_change_authorized": False,
    }
