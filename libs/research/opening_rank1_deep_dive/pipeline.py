from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .analysis import analyze
from .loaders import (
    load_actual_trades,
    load_opening_episodes,
    load_point_in_time_macro,
    load_q9_windows,
    load_symbol_metadata,
)
from .read_model import build_case
from .report import render_markdown


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    flattened = []
    for row in rows:
        copy = {key: value for key, value in row.items() if key != "actual_same_day_trades"}
        copy["themes"] = "|".join(copy.get("themes") or [])
        copy["sources"] = "|".join(copy.get("sources") or [])
        copy["actual_same_day_trade_count"] = len(row.get("actual_same_day_trades") or [])
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
        if value.get("delta") is not None and value.get("winner_n", 0) >= 10 and value.get("loser_n", 0) >= 10
    ]
    strongest = sorted(available, key=lambda item: abs(float(item[1]["delta"])), reverse=True)[:5]
    strongest = sorted(
        available,
        key=lambda item: abs(float(item[1].get("standardized_effect") or 0)),
        reverse=True,
    )[:5]
    statements = [
        "이 cohort의 유의미함은 `장초반 전체`가 아니라 `09:00~09:20의 당시 Rank-1을 결정 후 다음 분봉에 진입해 30분 보유`한 매우 제한된 조합에서만 관측됐습니다.",
        "5분·15분·30분·60분·EOD 성과가 같지 않고, 촘촘한 손절/익절 시뮬레이션은 음수였으므로 단순 초단타 신호가 아니라 초기 가격발견 후 15~30분 전개 가능성이 핵심 가설입니다.",
    ]
    if strongest:
        text = ", ".join(
            f"{key}(표준화 차이 {float(value['standardized_effect']):+.2f})"
            for key, value in strongest
        )
        statements.append(f"표본 10건 이상인 성분 중 승패의 표준화 차이가 크게 보인 항목은 {text} 순입니다.")
    path = analysis["path_patterns"]
    statements.append(
        "경로상 `5분 손실→30분 승리` "
        f"{path['negative_5m_then_30m_win']['count']}건, `5분 승리→30분 손실` "
        f"{path['positive_5m_then_30m_loss']['count']}건으로 초기 흔들림과 조기 페이드가 모두 존재합니다."
    )
    statements.append(
        "종목·일자 반복과 retrospective discovery가 있으므로 현재 결론은 `왜 후보가 보였는지에 대한 설명`이며, 독립적인 알파 확정이 아닙니다."
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
    metadata_path: Path = Path("data/research/opening_rank1_deep_dive/symbol_metadata_2026-07-31.json"),
    output_root: Path = Path("reports/evaluation/offline_alpha/opening_rank1_deep_dive"),
) -> dict[str, str]:
    episodes = load_opening_episodes(evidence_path)
    windows = load_q9_windows(reports_root, episodes)
    macro = load_point_in_time_macro(macro_logs_root, episodes)
    metadata = load_symbol_metadata(metadata_path)
    trades = load_actual_trades(reports_root, {str(row.get("day") or "") for row in episodes})
    cases = [
        build_case(
            row,
            window=windows.get(str(row.get("decision_id") or ""), {}),
            macro=macro.get(str(row.get("episode_id") or ""), {}),
            metadata=metadata.get(str(row.get("symbol") or ""), {}),
            actual_trades=trades.get((str(row.get("day") or ""), str(row.get("symbol") or "")), []),
        )
        for row in episodes
    ]
    result_analysis = analyze(cases)
    coverage = {
        "case_count": len(cases),
        "name_count": sum(bool(row.get("symbol_name")) for row in cases),
        "theme_count": sum(bool(row.get("themes")) for row in cases),
        "q9_count": sum(str(row.get("decision_id") or "") in windows for row in episodes),
        "macro_count": sum(bool(row.get("macro_observed_at")) for row in cases),
        "actual_trade_case_count": sum(bool(row.get("actual_same_day_trades")) for row in cases),
        "actual_opening_overlap_case_count": sum(
            any(bool(trade.get("overlaps_opening_window")) for trade in row.get("actual_same_day_trades") or [])
            for row in cases
        ),
        "tactic_id_count": sum(bool(row.get("tactic_id")) for row in cases),
        "strategist_scenario_count": sum(bool(row.get("strategist_scenario")) for row in cases),
        "score_breakdown_count": sum(row.get("score_momentum") is not None for row in cases),
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
    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(markdown_path)}
