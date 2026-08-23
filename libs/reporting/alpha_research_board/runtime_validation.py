from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from .loaders import load_json, mapping
from .sensitivity import leave_one_out, performance_metrics, performance_passes


CONTRACT_DATE = "2026-08-21"
REQUIRED_SESSIONS = 5
MIN_EPISODES = 5
VALID_DAY_STATUSES = {"VALID", "NO_OPENING_RANK1", "VALID_NO_EPISODES"}


def build_immediate_opening_runtime_validation(
    *, reports_root: Path, through_day: str
) -> dict[str, Any]:
    daily_root = reports_root / "evaluation" / "opening_rank1_shadow"
    session_rows = []
    for path in sorted(daily_root.glob("20??-??-??/opening_rank1_shadow_daily.json")):
        day = path.parent.name
        if day <= CONTRACT_DATE or day > through_day:
            continue
        payload, source = load_json(path)
        session_rows.append(
            {
                "day": day,
                "day_status": payload.get("day_status") or "MISSING",
                "source_error": source.get("error"),
                "path": str(path),
            }
        )
    fixed_sessions = session_rows[:REQUIRED_SESSIONS]
    fixed_days = {row["day"] for row in fixed_sessions}
    invalid_sessions = [
        row
        for row in fixed_sessions
        if row.get("source_error") or row.get("day_status") not in VALID_DAY_STATUSES
    ]

    cumulative, cumulative_source = load_json(
        daily_root / "opening_rank1_shadow_cumulative.json"
    )
    episodes = []
    eligible_total = 0
    for value in cumulative.get("episodes") or []:
        episode = mapping(value)
        if str(episode.get("day")) not in fixed_days:
            continue
        observability = mapping(episode.get("opening_observability"))
        lane = mapping(
            mapping(observability.get("conditional_lanes")).get("IMMEDIATE_OPENING_PROBE")
        )
        if not lane.get("eligible"):
            continue
        eligible_total += 1
        checkpoint = mapping(mapping(episode.get("checkpoints")).get("+5m"))
        net_return = checkpoint.get("live_net_return_pct")
        if net_return is None:
            continue
        asset = mapping(observability.get("asset_observation"))
        market = mapping(observability.get("market_snapshot"))
        episodes.append(
            {
                "day": episode.get("day"),
                "symbol": episode.get("symbol"),
                "decision_epoch": episode.get("decision_epoch"),
                "net_return_pct": net_return,
                "asset_class": asset.get("asset_class") or "UNKNOWN",
                "market_observed": market.get("kospi_pct") is not None,
            }
        )

    metrics = performance_metrics(episodes)
    symbol_counts = Counter(str(row.get("symbol")) for row in episodes)
    largest_symbol_share = (
        round(max(symbol_counts.values()) / len(episodes), 4) if episodes else None
    )
    asset_coverage = (
        round(sum(row["asset_class"] != "UNKNOWN" for row in episodes) / len(episodes), 4)
        if episodes
        else 0.0
    )
    market_coverage = (
        round(sum(bool(row["market_observed"]) for row in episodes) / len(episodes), 4)
        if episodes
        else 0.0
    )
    forward_coverage = round(len(episodes) / eligible_total, 4) if eligible_total else 1.0
    symbol_loo = leave_one_out(episodes, "symbol")
    day_loo = leave_one_out(episodes, "day")
    loo_pass = bool(symbol_loo) and bool(day_loo) and all(
        bool(row.get("passes")) for row in [*symbol_loo, *day_loo]
    )
    checks = {
        "session_count": len(fixed_sessions) == REQUIRED_SESSIONS,
        "session_integrity": not invalid_sessions,
        "minimum_episode_count": int(metrics.get("sample_count") or 0) >= MIN_EPISODES,
        "forward_coverage": forward_coverage >= 0.90,
        "average_return": float(metrics.get("avg_net_return_pct") or 0.0) > 0.0,
        "median_return": bool(episodes) and median(float(row["net_return_pct"]) for row in episodes) > 0.0,
        "profit_factor": float(metrics.get("profit_factor") or 0.0) >= 1.20,
        "win_rate": float(metrics.get("win_rate") or 0.0) >= 0.55,
        "asset_metadata": asset_coverage >= 0.80,
        "market_metadata": market_coverage >= 0.80,
        "symbol_concentration": largest_symbol_share is not None and largest_symbol_share <= 0.40,
        "leave_one_out": loo_pass,
    }
    window_complete = len(fixed_sessions) == REQUIRED_SESSIONS
    if not window_complete:
        decision = "COLLECTING"
        rationale = f"고정 5세션 중 {len(fixed_sessions)}세션 artifact가 생성됨."
    elif invalid_sessions or cumulative_source.get("error"):
        decision = "FAIL_RUNTIME_INTEGRITY"
        rationale = "고정 창에 invalid 일자 또는 누적 source 오류가 있음. 자동 연장하지 않음."
    elif int(metrics.get("sample_count") or 0) < MIN_EPISODES:
        decision = "INSUFFICIENT_RUNTIME_SAMPLE"
        rationale = "5세션 종료 시 독립 episode가 5건 미만임. 자동 연장하지 않음."
    elif not checks["forward_coverage"] or not checks["asset_metadata"] or not checks["market_metadata"]:
        decision = "FAIL_RUNTIME_INTEGRITY"
        rationale = "forward 또는 point-in-time metadata coverage가 고정 기준 미만임."
    elif not all(
        checks[key]
        for key in [
            "average_return",
            "median_return",
            "profit_factor",
            "win_rate",
            "symbol_concentration",
            "leave_one_out",
        ]
    ):
        decision = "FAIL_RUNTIME_EFFECT"
        rationale = "비용 차감 성과 또는 민감도 기준이 하나 이상 실패함."
    else:
        decision = "PASS_RUNTIME_VALIDATION"
        rationale = "고정 5세션의 효과·정합성·민감도 기준을 모두 통과함."
    return {
        "schema_version": "immediate_opening_runtime_validation.v1",
        "behavior_effect": "evaluation_only",
        "candidate_id": "IMMEDIATE_OPENING_PROBE",
        "contract_date": CONTRACT_DATE,
        "through_day": through_day,
        "required_sessions": REQUIRED_SESSIONS,
        "observed_session_count": len(fixed_sessions),
        "remaining_session_count": max(REQUIRED_SESSIONS - len(fixed_sessions), 0),
        "window_complete": window_complete,
        "sessions": fixed_sessions,
        "invalid_sessions": invalid_sessions,
        "eligible_episode_count": eligible_total,
        "metrics": metrics,
        "coverage": {
            "forward": forward_coverage,
            "asset_metadata": asset_coverage,
            "market_metadata": market_coverage,
        },
        "largest_symbol_share": largest_symbol_share,
        "checks": checks,
        "decision": decision,
        "rationale": rationale,
        "behavior_change_authorized": False,
        "episodes": episodes,
    }


def render_immediate_opening_runtime_validation(payload: Mapping[str, Any]) -> str:
    metrics = mapping(payload.get("metrics"))
    coverage = mapping(payload.get("coverage"))
    lines = [
        "# Immediate Opening Probe Runtime Validation",
        "",
        f"- 상태: `{payload.get('decision')}`",
        f"- 세션: {payload.get('observed_session_count', 0)} / {payload.get('required_sessions', 5)}",
        f"- 독립 episode: {metrics.get('sample_count', 0)}",
        f"- +5분 평균: {metrics.get('avg_net_return_pct')}",
        f"- 승률: {metrics.get('win_rate')}",
        f"- PF: {metrics.get('profit_factor')}",
        f"- forward coverage: {coverage.get('forward')}",
        f"- 자산 metadata coverage: {coverage.get('asset_metadata')}",
        f"- 시장 metadata coverage: {coverage.get('market_metadata')}",
        "",
        str(payload.get("rationale") or ""),
        "",
        "| Day | Status | Source error |",
        "|---|---|---|",
    ]
    for value in payload.get("sessions") or []:
        row = mapping(value)
        lines.append(
            f"| {row.get('day')} | `{row.get('day_status')}` | `{row.get('source_error') or '-'}` |"
        )
    lines.extend(
        [
            "",
            "이 보고서는 기존 observer를 읽기만 하며 매매 행동을 변경하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)
