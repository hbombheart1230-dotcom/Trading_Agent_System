from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .analysis import analyze
from .loaders import (
    load_actual_trades,
    load_all_q9_windows,
    load_opening_episodes,
    load_point_in_time_macro,
    load_q9_windows,
    load_symbol_metadata,
)
from .microstructure import load_minute_rows, microstructure_features
from .rank_context import build_rank_index, rank_features
from .read_model import build_case
from .report import render_markdown


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    flattened = []
    for row in rows:
        copy = {
            key: value
            for key, value in row.items()
            if key != "actual_same_day_trades"
        }
        copy["themes"] = "|".join(copy.get("themes") or [])
        copy["sources"] = "|".join(copy.get("sources") or [])
        copy["actual_same_day_trade_count"] = len(
            row.get("actual_same_day_trades") or []
        )
        flattened.append(copy)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in flattened for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flattened)


def _findings(analysis: dict[str, Any]) -> list[str]:
    features = analysis["winner_loser"]["features"]
    available = [
        (key, value)
        for key, value in features.items()
        if value.get("delta") is not None
        and value.get("winner_n", 0) >= 10
        and value.get("loser_n", 0) >= 10
        and key
        not in {
            "rank1_next5m_observations",
            "rank1_forward_persistence_sec",
            "path_high_vs_prior_close_pct",
        }
    ]
    strongest = sorted(
        available,
        key=lambda item: abs(float(item[1].get("standardized_effect") or 0)),
        reverse=True,
    )[:5]
    statements = [
        "This is a narrow 09:00-09:19 pre-Strategist intrinsic Rank-1 plus fixed 30-minute observation cohort, not a general opening-market result.",
        "Returns differed sharply by exact decision time, and many winners experienced opening noise before their 15-30 minute expansion.",
    ]
    if strongest:
        feature_text = ", ".join(
            f"{key} (standardized difference "
            f"{float(value['standardized_effect']):+.2f})"
            for key, value in strongest
        )
        statements.append(
            "Among features with at least 10 winner and loser observations, the "
            f"largest descriptive differences were: {feature_text}."
        )
    path = analysis["path_patterns"]
    statements.append(
        "The path included "
        f"{path['negative_5m_then_30m_win']['count']} negative-5m/positive-30m "
        "cases and "
        f"{path['positive_5m_then_30m_loss']['count']} "
        "positive-5m/non-positive-30m cases."
    )
    statements.append(
        "Repeated symbols, repeated days, and retrospective screen discovery mean "
        "this is a prospective hypothesis, not a production policy."
    )
    arcs = analysis.get("by_price_arc") or {}
    normal = arcs.get("NORMAL") or {}
    limit_up = arcs.get("LIMIT_UP_TRAJECTORY") or {}
    crash = arcs.get("CRASH_REVERSAL") or {}
    statements.append(
        "The aggregate edge was concentrated in rare paths: "
        f"NORMAL {normal.get('count', 0)} cases averaged "
        f"{float(normal.get('avg_return_pct') or 0):+.3f}%, "
        f"LIMIT_UP_TRAJECTORY {limit_up.get('count', 0)} cases averaged "
        f"{float(limit_up.get('avg_return_pct') or 0):+.3f}%, and CRASH_REVERSAL "
        f"{crash.get('count', 0)} cases averaged "
        f"{float(crash.get('avg_return_pct') or 0):+.3f}%."
    )
    statements.append(
        "The only broad pre-decision screen left is the 09:00-09:04 decision "
        "window. Completed-minute relative volume is unavailable for decisions "
        "inside the first minute and must not be reconstructed from future bars."
    )
    return statements


def run_opening_rank1_deep_dive(
    *,
    evidence_path: Path = Path(
        "reports/evaluation/offline_alpha/existing_evidence_mining/"
        "2026-06-01_2026-07-30/existing_evidence_mining.json"
    ),
    reports_root: Path = Path("reports"),
    macro_logs_root: Path = Path("data/logs/macro_indicators"),
    metadata_path: Path = Path(
        "data/research/opening_rank1_deep_dive/symbol_metadata_2026-07-31.json"
    ),
    minute_cache_root: Path = Path(
        "data/research/post_reclaim_alpha/minute_cache"
    ),
    output_root: Path = Path(
        "reports/evaluation/offline_alpha/opening_rank1_deep_dive"
    ),
) -> dict[str, str]:
    episodes = load_opening_episodes(evidence_path)
    windows = load_q9_windows(reports_root, episodes)
    all_windows = load_all_q9_windows(
        reports_root,
        {str(row.get("day") or "") for row in episodes},
    )
    macro = load_point_in_time_macro(macro_logs_root, episodes)
    metadata = load_symbol_metadata(metadata_path)
    trades = load_actual_trades(
        reports_root,
        {str(row.get("day") or "") for row in episodes},
    )
    minute_rows = load_minute_rows(
        minute_cache_root,
        {str(row.get("symbol") or "") for row in episodes},
    )
    rank_index = build_rank_index(all_windows)
    cases = [
        build_case(
            row,
            window=windows.get(str(row.get("decision_id") or ""), {}),
            macro=macro.get(str(row.get("episode_id") or ""), {}),
            metadata=metadata.get(str(row.get("symbol") or ""), {}),
            actual_trades=trades.get(
                (str(row.get("day") or ""), str(row.get("symbol") or "")),
                [],
            ),
        )
        for row in episodes
    ]
    for case in cases:
        case.update(
            microstructure_features(
                case,
                minute_rows.get(str(case.get("symbol") or ""), []),
            )
        )
        case.update(
            rank_features(
                case,
                decision_id=str(case.get("decision_id") or ""),
                rank_index=rank_index,
            )
        )
    result_analysis = analyze(cases)
    coverage = {
        "case_count": len(cases),
        "name_count": sum(bool(row.get("symbol_name")) for row in cases),
        "theme_count": sum(bool(row.get("themes")) for row in cases),
        "q9_count": sum(
            str(row.get("decision_id") or "") in windows
            for row in episodes
        ),
        "macro_count": sum(
            bool(row.get("macro_observed_at"))
            for row in cases
        ),
        "actual_trade_case_count": sum(
            bool(row.get("actual_same_day_trades"))
            for row in cases
        ),
        "actual_opening_overlap_case_count": sum(
            any(
                bool(trade.get("overlaps_opening_window"))
                for trade in row.get("actual_same_day_trades") or []
            )
            for row in cases
        ),
        "tactic_id_count": sum(bool(row.get("tactic_id")) for row in cases),
        "strategist_scenario_count": sum(
            bool(row.get("strategist_scenario"))
            for row in cases
        ),
        "score_breakdown_count": sum(
            row.get("score_momentum") is not None
            for row in cases
        ),
        "microstructure_count": sum(
            row.get("microstructure_status") == "OBSERVED"
            for row in cases
        ),
        "rank_context_count": sum(
            row.get("rank_context_status") == "OBSERVED"
            for row in cases
        ),
    }
    payload = {
        "schema_version": "opening_rank1_deep_dive.v1",
        "behavior_effect": "offline_analysis_only",
        "cohort": "OPEN_0_20_RANK1_30M",
        "coverage": coverage,
        "cases": cases,
        "analysis": result_analysis,
        "findings": _findings(result_analysis),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "opening_rank1_deep_dive.json"
    csv_path = output_root / "opening_rank1_cases.csv"
    markdown_path = output_root / "opening_rank1_deep_dive.md"
    _write_json(json_path, payload)
    _write_csv(csv_path, cases)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(markdown_path),
    }
