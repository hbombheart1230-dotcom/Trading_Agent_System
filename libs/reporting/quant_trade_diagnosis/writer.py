from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from libs.reporting.evaluation.artifact_inventory import iter_trade_dirs, read_json
from libs.reporting.evaluation.counterfactuals import build_selection_attribution
from libs.reporting.evaluation.trade_evaluator import evaluate_trade
from libs.reporting.evaluation.trade_read_model import build_q9_trade_read_model

from .builder import build_quant_trade_diagnosis
from .markdown import render_quant_trade_diagnosis


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_quant_trade_diagnosis(
    *,
    trade_dir: Path,
    payload: Mapping[str, Any],
) -> dict[str, str]:
    reports_dir = Path(trade_dir) / "reports"
    json_path = reports_dir / "quant_trade_diagnosis.json"
    markdown_path = reports_dir / "quant_trade_diagnosis.md"
    _write_json(json_path, payload)
    markdown_path.write_text(
        render_quant_trade_diagnosis(payload),
        encoding="utf-8",
    )
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }


def write_quant_trade_diagnoses_for_day(
    *,
    reports_root: Path,
    day: str,
    trade_dirs: Iterable[Path] | None = None,
    models: Iterable[Mapping[str, Any]] | None = None,
    evaluations: Iterable[Mapping[str, Any]] | None = None,
    attributions: Iterable[Mapping[str, Any]] | None = None,
    root_cause_report: Mapping[str, Any] | None = None,
    entry_timing_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    resolved_dirs = list(trade_dirs or iter_trade_dirs(reports_root, day))
    resolved_models = (
        [dict(row) for row in models]
        if models is not None
        else [build_q9_trade_read_model(path) for path in resolved_dirs]
    )
    resolved_evaluations = (
        [dict(row) for row in evaluations]
        if evaluations is not None
        else [evaluate_trade(model) for model in resolved_models]
    )
    resolved_attributions = (
        [dict(row) for row in attributions]
        if attributions is not None
        else [build_selection_attribution(model) for model in resolved_models]
    )
    daily = reports_root / "evaluation" / "daily" / day
    root_cause = dict(
        root_cause_report
        if root_cause_report is not None
        else read_json(daily / "scanner_alignment_root_cause_report.json")
    )
    entry_timing = dict(
        entry_timing_report
        if entry_timing_report is not None
        else read_json(daily / "entry_timing_attribution_report.json")
    )

    written = []
    for trade_dir, model, evaluation, attribution in zip(
        resolved_dirs,
        resolved_models,
        resolved_evaluations,
        resolved_attributions,
    ):
        payload = build_quant_trade_diagnosis(
            trade_dir=trade_dir,
            model=model,
            evaluation=evaluation,
            attribution=attribution,
            root_cause_report=root_cause,
            entry_timing_report=entry_timing,
            all_models=resolved_models,
        )
        paths = write_quant_trade_diagnosis(trade_dir=trade_dir, payload=payload)
        written.append(
            {
                "trade_id": model.get("trade_id"),
                "symbol": model.get("symbol"),
                **paths,
            }
        )
    return {
        "schema_version": "quant_trade_diagnosis_batch.v1",
        "behavior_effect": "diagnostic_only",
        "day": day,
        "trade_count": len(resolved_models),
        "written_count": len(written),
        "written": written,
    }
