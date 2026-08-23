from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from .loaders import find_by_id, load_json, mapping, metric_snapshot
from .sensitivity import leave_one_out, performance_metrics, performance_passes


def _opening_rows(
    payload: Mapping[str, Any], *, lane_id: str, horizon: str
) -> list[dict[str, Any]]:
    rows = []
    for value in payload.get("episodes") or []:
        episode = mapping(value)
        observability = mapping(episode.get("opening_observability"))
        lane = mapping(mapping(observability.get("conditional_lanes")).get(lane_id))
        checkpoint = mapping(mapping(episode.get("checkpoints")).get(horizon))
        net_return = checkpoint.get("live_net_return_pct")
        if not lane.get("eligible") or net_return is None:
            continue
        asset = mapping(observability.get("asset_observation"))
        market = mapping(observability.get("market_snapshot"))
        rows.append(
            {
                "day": episode.get("day"),
                "symbol": episode.get("symbol"),
                "decision_epoch": episode.get("decision_epoch"),
                "net_return_pct": net_return,
                "asset_class": asset.get("asset_class") or "UNKNOWN",
                "kospi_pct": market.get("kospi_pct"),
            }
        )
    return rows


def _bounded_review(
    rows: Sequence[Mapping[str, Any]], *, minimum_sample: int
) -> dict[str, Any]:
    base = performance_metrics(rows)
    symbol_loo = leave_one_out(rows, "symbol")
    day_loo = leave_one_out(rows, "day")
    worst_symbol = symbol_loo[0] if symbol_loo else {}
    worst_day = day_loo[0] if day_loo else {}
    best = max(rows, key=lambda row: float(row["net_return_pct"])) if rows else None
    without_best = performance_metrics([row for row in rows if row is not best])
    day_counts = Counter(str(row.get("day")) for row in rows)
    symbol_counts = Counter(str(row.get("symbol")) for row in rows)
    if int(base.get("sample_count") or 0) < minimum_sample:
        decision = "RUNTIME_DATA_REQUIRED"
        rationale = (
            f"독립 episode {base.get('sample_count', 0)}건으로 최소 {minimum_sample}건에 미달함."
        )
    elif not performance_passes(base):
        decision = "REJECT_BASE_EFFECT"
        rationale = "기본 비용 차감 성과가 평균/PF 기준을 통과하지 못함."
    elif not bool(worst_symbol.get("passes")):
        decision = "REJECT_SYMBOL_CONTRIBUTOR_DEPENDENCE"
        rationale = (
            f"종목 {worst_symbol.get('excluded_symbol')} 제외 시 평균/PF 기준이 무너짐."
        )
    elif not bool(worst_day.get("passes")):
        decision = "REJECT_DAY_CONTRIBUTOR_DEPENDENCE"
        rationale = f"일자 {worst_day.get('excluded_day')} 제외 시 평균/PF 기준이 무너짐."
    elif not performance_passes(without_best):
        decision = "REJECT_SINGLE_OBSERVATION_DEPENDENCE"
        rationale = "최대 단일 수익을 제외하면 평균/PF 기준이 무너짐."
    else:
        decision = "READY_FOR_FIXED_RUNTIME_VALIDATION"
        rationale = "기본 성과와 종목·일자·최대 수익 제거 민감도를 모두 통과함."
    return {
        "base": base,
        "minimum_sample": minimum_sample,
        "largest_day_share": round(max(day_counts.values()) / len(rows), 4) if rows else None,
        "largest_symbol_share": round(max(symbol_counts.values()) / len(rows), 4) if rows else None,
        "sensitivity": {
            "worst_symbol_leave_one_out": worst_symbol,
            "worst_day_leave_one_out": worst_day,
            "without_best_observation": without_best,
        },
        "decision": decision,
        "rationale": rationale,
    }


def evaluate_bounded_candidate(
    rows: Sequence[Mapping[str, Any]], *, minimum_sample: int
) -> dict[str, Any]:
    return _bounded_review(rows, minimum_sample=minimum_sample)


def _btc_review(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for value in payload.get("episodes") or []:
        episode = mapping(value)
        checkpoint = mapping(mapping(episode.get("returns")).get("+30m"))
        gross = checkpoint.get("return_pct")
        if gross is None:
            continue
        rows.append(
            {
                "day": episode.get("day"),
                "symbol": "041190",
                "decision_epoch": episode.get("start_epoch"),
                "net_return_pct": round(float(gross) - 0.28, 4),
                "btc_regime": mapping(episode.get("btc")).get("market_regime") or "UNKNOWN",
            }
        )
    base = performance_metrics(rows)
    day_loo = leave_one_out(rows, "day")
    worst_day = day_loo[0] if day_loo else {}
    best = max(rows, key=lambda row: float(row["net_return_pct"])) if rows else None
    without_best = performance_metrics([row for row in rows if row is not best])
    by_regime = []
    for regime in sorted({str(row.get("btc_regime")) for row in rows}):
        by_regime.append(
            {
                "btc_regime": regime,
                **performance_metrics([row for row in rows if row.get("btc_regime") == regime]),
            }
        )
    if not performance_passes(base):
        decision = "REJECT_BASE_EFFECT"
        rationale = "BTC-우기투 +30분 기본 성과가 기준을 통과하지 못함."
    elif not bool(worst_day.get("passes")):
        decision = "REJECT_DAY_CONTRIBUTOR_DEPENDENCE"
        rationale = (
            f"{worst_day.get('excluded_day')} 제외 시 평균/PF가 기준 미만으로 내려가 일반 신호로 볼 수 없음."
        )
    elif not performance_passes(without_best):
        decision = "REJECT_SINGLE_OBSERVATION_DEPENDENCE"
        rationale = "최대 수익 관측을 제외하면 성과 기준이 무너짐."
    else:
        decision = "READY_FOR_FIXED_RUNTIME_VALIDATION"
        rationale = "기존 episode에서 일자·최대 수익 민감도를 통과함."
    return {
        "base": base,
        "sensitivity": {
            "worst_day_leave_one_out": worst_day,
            "without_best_observation": without_best,
        },
        "by_btc_regime": by_regime,
        "decision": decision,
        "rationale": rationale,
    }


def build_remaining_candidate_reviews(
    *, reports_root: Path, through_day: str
) -> dict[str, Any]:
    opening, opening_source = load_json(
        reports_root / "evaluation" / "opening_rank1_shadow" / "opening_rank1_shadow_cumulative.json"
    )
    btc, btc_source = load_json(
        reports_root
        / "evaluation"
        / "baseline_btc_woori_tech"
        / "historical"
        / "q12_v1_v2_historical_review.json"
    )
    prospective, prospective_source = load_json(
        reports_root
        / "evaluation"
        / "feature_mart"
        / "opening_rank1"
        / "prospective"
        / "rank1_candidate_shadow_cumulative.json"
    )
    post_cross = find_by_id(
        prospective.get("candidate_summaries"),
        "candidate_id",
        "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1",
    )
    post_cross_branch = metric_snapshot(post_cross.get("branch"))
    reviews = [
        {
            "candidate_id": "IMMEDIATE_OPENING_PROBE",
            "target_horizon": "+5m",
            **_bounded_review(
                _opening_rows(opening, lane_id="IMMEDIATE_OPENING_PROBE", horizon="+5m"),
                minimum_sample=10,
            ),
        },
        {
            "candidate_id": "CONFIRMED_RECURRENT_RANK",
            "target_horizon": "+30m",
            **_bounded_review(
                _opening_rows(opening, lane_id="CONFIRMED_RECURRENT_RANK", horizon="+30m"),
                minimum_sample=5,
            ),
        },
        {
            "candidate_id": "DISLOCATION_REBOUND",
            "target_horizon": "+60m",
            **_bounded_review(
                _opening_rows(opening, lane_id="DISLOCATION_REBOUND", horizon="+60m"),
                minimum_sample=5,
            ),
        },
        {
            "candidate_id": "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1",
            "target_horizon": "+15m",
            "base": post_cross_branch,
            "decision": "REJECT_PROSPECTIVE_EFFECT_NOT_CONFIRMED",
            "rationale": "과거 양수 방향이 prospective 평균/PF에서 재현되지 않음.",
        },
        {
            "candidate_id": "BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION",
            "target_horizon": "+30m",
            **_btc_review(btc),
        },
        {
            "candidate_id": "SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1",
            "target_horizon": "+180m",
            "base": {"sample_count": 1},
            "decision": "RUNTIME_DATA_REQUIRED",
            "rationale": "2026-08-21 정합성 수정 이후 독립 거래일이 1일뿐임.",
        },
    ]
    next_runtime = [
        row["candidate_id"]
        for row in reviews
        if row["decision"] == "READY_FOR_FIXED_RUNTIME_VALIDATION"
    ]
    background_runtime = [
        row["candidate_id"]
        for row in reviews
        if row["decision"] == "RUNTIME_DATA_REQUIRED"
    ]
    return {
        "schema_version": "remaining_candidate_reviews.v1",
        "behavior_effect": "evaluation_only",
        "through_day": through_day,
        "decision_contract": {
            "minimum_avg_net_return_pct": 0.0,
            "minimum_profit_factor": 1.2,
            "sensitivity": "all single-symbol/day and maximum-observation removals must pass",
        },
        "reviews": reviews,
        "next_fixed_runtime_candidate": next_runtime[0] if len(next_runtime) == 1 else None,
        "background_runtime_measurement": background_runtime,
        "source_integrity": {
            "opening": opening_source.get("error"),
            "btc": btc_source.get("error"),
            "prospective": prospective_source.get("error"),
        },
        "behavior_change_authorized": False,
    }


def render_remaining_candidate_reviews(payload: Mapping[str, Any]) -> str:
    def metric(metrics: Any) -> str:
        row = mapping(metrics)
        count = int(row.get("sample_count") or 0)
        if not count:
            return "-"
        win = row.get("win_rate")
        avg = row.get("avg_net_return_pct")
        pf = row.get("profit_factor")
        return (
            f"N={count}, WR {'-' if win is None else f'{float(win) * 100:.1f}%'}, "
            f"avg {'-' if avg is None else f'{float(avg):+.4f}%'}, "
            f"PF {'-' if pf is None else f'{float(pf):.4f}'}"
        )

    lines = [
        f"# Remaining Candidate Reviews - {payload.get('through_day')}",
        "",
        "기존 데이터로 가능한 판정을 모두 끝낸 결과입니다. 행동 변경은 없습니다.",
        "",
        "| 후보 | Horizon | 기존 성과 | 판정 | 근거 |",
        "|---|---|---|---|---|",
    ]
    for value in payload.get("reviews") or []:
        row = mapping(value)
        lines.append(
            f"| `{row.get('candidate_id')}` | `{row.get('target_horizon')}` | "
            f"{metric(row.get('base'))} | `{row.get('decision')}` | {row.get('rationale')} |"
        )
    lines.extend(
        [
            "",
            "## 실제 런 이전 결론",
            "",
            f"- 다음 고정 런 검증 후보: `{payload.get('next_fixed_runtime_candidate') or 'NONE'}`",
            f"- 행동과 무관하게 계속 측정할 항목: `{', '.join(payload.get('background_runtime_measurement') or []) or 'NONE'}`",
            "- 기각 후보는 threshold를 바꾸거나 이름을 바꿔 재개하지 않습니다.",
            "- 실제 런에서도 기존 observer artifact만 사용하며 주문·진입·청산은 변경하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)
