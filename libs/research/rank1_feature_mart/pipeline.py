from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .builder import build_episode
from .candidates import select_candidates
from .contracts import BEHAVIOR_EFFECT, CORE_FEATURE_PATHS, LIVE_COST_PCT, OUTCOME_LABELS, SCHEMA_VERSION
from .integrity import audit
from .loaders import historical_episodes, longitudinal_events, prospective_episodes, q9_windows, refresh_source_caches, source_rows
from .report import render_integrity, render_summary
from .trees import build_all_trees
from .strategy_alignment_report import write_strategy_alignment_reports


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def run(
    *,
    project_root: Path,
    output_root: Path | None = None,
    refresh_sources: bool = False,
    refresh_from_day: str = "2026-08-01",
    base_day: str = "2026-08-11",
) -> dict[str, Any]:
    reports_root = project_root / "reports"
    historical_path = reports_root / "evaluation" / "offline_alpha" / "conditional_alpha_diagnosis" / "conditional_alpha_episode_contexts.json"
    prospective_path = reports_root / "evaluation" / "opening_rank1_shadow" / "opening_rank1_shadow_cumulative.json"
    longitudinal_path = reports_root / "evaluation" / "offline_alpha" / "opening_rank1_longitudinal" / "opening_rank1_longitudinal.json"
    output_root = output_root or reports_root / "evaluation" / "feature_mart" / "opening_rank1"

    historical = historical_episodes(historical_path)
    prospective = prospective_episodes(prospective_path)
    all_sources = [*historical, *prospective]
    windows = q9_windows(reports_root, all_sources)
    symbols = {str(row.get("symbol") or "").zfill(6) for row in all_sources if row.get("symbol")}
    minute_cache_root = project_root / "data" / "research" / "post_reclaim_alpha" / "minute_cache"
    daily_cache_root = project_root / "data" / "research" / "opening_rank1_longitudinal" / "daily_cache"
    refresh_meta = None
    if refresh_sources:
        refresh_meta = refresh_source_caches(
            minute_cache_root=minute_cache_root,
            daily_cache_root=daily_cache_root,
            symbols=symbols,
            refresh_from_day=refresh_from_day,
            base_day=base_day,
        )
    minute_by_symbol, daily_by_symbol = source_rows(
        minute_cache_root=minute_cache_root,
        daily_cache_root=daily_cache_root,
        symbols=symbols,
        additional_minute_cache_roots=(
            project_root / "data" / "research" / "opening_rank1_shadow" / "minute_cache",
        ),
    )
    longitudinal = longitudinal_events(longitudinal_path)
    rows: list[dict[str, Any]] = []
    for source, is_prospective in ((historical, False), (prospective, True)):
        for item in source:
            symbol = str(item.get("symbol") or "").zfill(6)
            episode_id = str(item.get("episode_id") or "")
            rows.append(
                build_episode(
                    row=item,
                    prospective=is_prospective,
                    window=windows.get(str(item.get("decision_id") or ""), {}),
                    minute_rows=minute_by_symbol.get(symbol, []),
                    daily_rows=daily_by_symbol.get(symbol, []),
                    longitudinal=longitudinal.get(episode_id, {}),
                )
            )
    deduplicated = {str(row["identity"]["episode_id"]): row for row in rows}
    rows = sorted(deduplicated.values(), key=lambda row: (row["identity"]["day"], row["identity"]["decision_epoch"], row["identity"]["symbol"]))
    integrity = audit(rows)
    trees = build_all_trees(rows)
    candidates = select_candidates(rows)
    schema = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": BEHAVIOR_EFFECT,
        "round_trip_cost_pct": LIVE_COST_PCT,
        "core_feature_paths": list(CORE_FEATURE_PATHS),
        "outcome_labels": list(OUTCOME_LABELS),
        "point_in_time_rule": "Only minute bars fully closed at decision_epoch may become features.",
        "market_snapshot_contract": {
            "schema_version": "opening_rank1_market_snapshot.v1",
            "selection_policy": "LATEST_AT_OR_BEFORE_DECISION",
            "required_fields": [
                "snapshot_epoch",
                "snapshot_time_kst",
                "snapshot_age_sec",
                "source_path",
                "kospi_pct",
                "kosdaq_pct",
                "kospi200_pct",
                "krx_night_futures_pct",
                "evidence_status",
            ],
            "future_snapshot_allowed": False,
        },
        "responsibility_split": {
            "scanner": "candidate suitability and rank quality",
            "entry": "chart state and timing after selection",
            "horizon": "holding-period suitability without changing exits",
        },
    }
    _write_json(output_root / "schema.json", schema)
    _write_json(output_root / "feature_mart.json", {"schema_version": SCHEMA_VERSION, "episodes": rows})
    months: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        months.setdefault(str(row["identity"]["day"])[:7], []).append(row)
    for month, month_rows in months.items():
        _write_jsonl(output_root / "episodes" / f"{month}.jsonl", month_rows)
    _write_json(output_root / "integrity_report.json", integrity)
    (output_root / "integrity_report.md").write_text(render_integrity(integrity), encoding="utf-8")
    for name in ("scanner", "entry", "horizon"):
        payload = trees[name]
        _write_json(output_root / f"{name}_tree.json", payload)
    _write_json(output_root / "horizon_matrix.json", trees["horizon_matrix"])
    _write_json(output_root / "candidate_selection.json", candidates)
    strategy_alignment = write_strategy_alignment_reports(
        rows, output_root=output_root
    )
    if refresh_meta is not None:
        _write_json(output_root / "source_refresh.json", refresh_meta)
    (output_root / "feature_mart_report.md").write_text(render_summary(rows, integrity, trees, candidates), encoding="utf-8")
    return {
        "output_root": str(output_root),
        "episode_count": len(rows),
        "integrity": integrity,
        "trees": trees,
        "candidates": candidates,
        "strategy_alignment": strategy_alignment,
        "source_refresh": refresh_meta,
    }
