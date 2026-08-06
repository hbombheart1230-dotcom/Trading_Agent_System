from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def load_trade_observations(
    reports_root: Path,
    *,
    start_day: str,
    end_day: str,
) -> list[dict[str, Any]]:
    trade_source_by_id = {
        path.parent.parent.name: path
        for path in reports_root.glob("trades/**/reports/post_exit_shadow_recap.json")
    }
    rows: list[dict[str, Any]] = []
    root = reports_root / "evaluation" / "trades"
    for model_path in sorted(root.glob("**/trade_read_model.json")):
        model = read_json(model_path)
        day = str(model.get("day") or "")[:10]
        if not (start_day <= day <= end_day):
            continue
        trade_id = str(model.get("trade_id") or model_path.parent.name)
        evaluation = read_json(model_path.with_name("trade_evaluation.json"))
        recap_path = trade_source_by_id.get(trade_id)
        recap = read_json(recap_path) if recap_path else {}
        rows.append(
            {
                "trade_id": trade_id,
                "day": day,
                "symbol": str(model.get("symbol") or ""),
                "model": model,
                "evaluation": evaluation,
                "post_exit_recap": recap,
                "model_path": str(model_path),
                "recap_path": str(recap_path or ""),
            }
        )
    return rows


def load_latest_q16_review(reports_root: Path, *, end_day: str) -> dict[str, Any]:
    paths = sorted(
        path
        for path in (reports_root / "evaluation" / "daily").glob("*/q16_proxy_rejection_review.json")
        if path.parent.name <= end_day
    )
    return read_json(paths[-1]) if paths else {}


def load_stage_review_inventory(
    reports_root: Path,
    *,
    start_day: str,
    end_day: str,
) -> dict[str, Any]:
    llm_root = reports_root / "llm"
    counts = {"stage3": 0, "stage4": 0}
    days = {"stage3": set(), "stage4": set()}
    for stage, folder in (
        ("stage3", "strategist_stage3_hold_review"),
        ("stage4", "strategist_stage4_carry_review"),
    ):
        for path in llm_root.glob(f"**/{folder}/response.json"):
            parts = path.parts
            day = next((part for part in parts if len(part) == 10 and part[4:5] == "-"), "")
            if not day or not (start_day <= day <= end_day):
                continue
            counts[stage] += 1
            days[stage].add(day)
    return {
        "stage3_call_count": counts["stage3"],
        "stage3_day_count": len(days["stage3"]),
        "stage4_call_count": counts["stage4"],
        "stage4_day_count": len(days["stage4"]),
    }
