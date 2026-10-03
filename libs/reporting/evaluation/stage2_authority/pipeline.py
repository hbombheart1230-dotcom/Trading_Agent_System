from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from libs.reporting.evaluation.full_chain_component_review import _q9_decision_candidate_rows
from libs.reporting.quant_shadow_candidate_evaluation import load_quant_shadow_candidate_payloads_for_range

from .builder import build_stage2_authority_records, build_stage2_authority_review
from .contracts import SCHEMA_VERSION
from .deep_dive import build_stage2_effectiveness_deep_dive
from .deep_dive_report import render_stage2_effectiveness_deep_dive
from .loaders import load_q9_windows, load_stage2_responses
from .report import render_stage2_authority_review


def _write_payload(payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "strategist_stage2_authority_review.json"
    markdown_path = output_dir / "strategist_stage2_authority_review.md"
    deep_dive = build_stage2_effectiveness_deep_dive(
        start=str(_mapping(payload.get("range")).get("start") or ""),
        end=str(_mapping(payload.get("range")).get("end") or ""),
        records=[row for row in payload.get("records") or [] if isinstance(row, dict)],
    )
    deep_json_path = output_dir / "strategist_stage2_effectiveness_deep_dive.json"
    deep_markdown_path = output_dir / "strategist_stage2_effectiveness_deep_dive.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_stage2_authority_review(payload), encoding="utf-8")
    deep_json_path.write_text(json.dumps(deep_dive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    deep_markdown_path.write_text(render_stage2_effectiveness_deep_dive(deep_dive), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "deep_dive_json_path": str(deep_json_path),
        "deep_dive_markdown_path": str(deep_markdown_path),
        "range": payload.get("range"),
        "authorities": payload.get("authorities"),
    }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _iter_days(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start[:10])
    final = date.fromisoformat(end[:10])
    days: list[str] = []
    while current <= final:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _day_has_refresh_evidence(reports_root: Path, day: str) -> bool:
    scorecard = _read_json(
        reports_root
        / "evaluation"
        / "agent_effectiveness"
        / day
        / "agent_effectiveness_scorecard.json"
    )
    components = scorecard.get("components") if isinstance(scorecard.get("components"), dict) else {}
    strategist = components.get("strategist") if isinstance(components.get("strategist"), dict) else {}
    refresh = strategist.get("post_scanner_refresh") if isinstance(strategist.get("post_scanner_refresh"), dict) else {}
    return int(refresh.get("comparison_count") or 0) > 0


def write_stage2_authority_review(
    *,
    reports_root: Path,
    start: str,
    end: str,
    output_dir: Path,
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    payloads = load_quant_shadow_candidate_payloads_for_range(
        reports_root=reports_root,
        start=start,
        end=end,
    )
    candidate_rows = _q9_decision_candidate_rows(payloads)
    records = build_stage2_authority_records(
        candidate_rows=candidate_rows,
        windows=load_q9_windows(reports_root, start, end),
        responses=load_stage2_responses(reports_root, start, end),
    )
    payload = build_stage2_authority_review(start=start, end=end, records=records)
    return _write_payload(payload, output_dir)


def write_stage2_authority_review_sharded(
    *,
    reports_root: Path,
    start: str,
    end: str,
    output_dir: Path,
    rebuild_daily: bool = False,
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    daily_root = reports_root / "evaluation" / "agent_effectiveness"
    records_by_id: dict[str, dict[str, Any]] = {}
    shard_days: list[str] = []
    for day in _iter_days(start, end):
        if not _day_has_refresh_evidence(reports_root, day):
            continue
        day_dir = daily_root / day
        review_path = day_dir / "strategist_stage2_authority_review.json"
        payload = {} if rebuild_daily else _read_json(review_path)
        if payload.get("schema_version") != SCHEMA_VERSION:
            write_stage2_authority_review(
                reports_root=reports_root,
                start=day,
                end=day,
                output_dir=day_dir,
            )
            payload = _read_json(review_path)
        shard_days.append(day)
        for raw in payload.get("records") or []:
            if not isinstance(raw, dict):
                continue
            decision_id = str(raw.get("decision_id") or "").strip()
            if decision_id:
                records_by_id[decision_id] = dict(raw)
    cumulative = build_stage2_authority_review(
        start=start,
        end=end,
        records=list(records_by_id.values()),
    )
    cumulative["aggregation"] = {
        "method": "exact_daily_shards_deduped_by_decision_id",
        "shard_days": shard_days,
        "shard_count": len(shard_days),
        "deduplicated_record_count": len(records_by_id),
    }
    return _write_payload(cumulative, output_dir)
